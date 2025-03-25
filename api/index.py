from flask import Flask, request, jsonify
import os
import aiohttp
import asyncio
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

app = Flask(__name__)

cookies = {
    'PANWEB': '1',
    'browserid': 'JtVMCPCo6G2oBd8twkc4on5badfdewoLzTSzSYo1YcSHvLDdqHpnXBuj5-s=',
    'lang': 'en',
    '__bid_n': '195cb42b7a1e32ec464207',
    'ndut_fmt': '1DF36D6E6EBD12E789FFF501095DAF2C6505282E1607C97DDA6CDC0D820B3AAD',
    '__stripe_mid': 'b85d61d2-4812-4eeb-8e41-b1efb3fa2a002a54d5',
    'csrfToken': 'PR31Fzq6f3GTxKvvLB1XcYPN',
    '__stripe_sid': 'e8fd1495-017f-4f05-949c-7cb3a1c780fed92613',
    'ndus': 'YylKpiCteHuiYEqq8n75Tb-JhCqmg0g4YMH03MYD',
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Priority': 'u=0, i',
}


def find_between(string, start, end):
    start_index = string.find(start) + len(start)
    end_index = string.find(end, start_index)
    return string[start_index:end_index]


async def fetch_download_link_async(url):
    try:
        async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
            async with session.get(url) as response1:
                response1.raise_for_status()
                response_data = await response1.text()
                js_token = find_between(response_data, 'fn%28%22', '%22%29')
                log_id = find_between(response_data, 'dp-logid=', '&')

                if not js_token or not log_id:
                    return None

                request_url = str(response1.url)
                surl = request_url.split('surl=')[1]
                params = {
                    'app_id': '250528',
                    'web': '1',
                    'channel': 'dubox',
                    'clienttype': '0',
                    'jsToken': js_token,
                    'dplogid': log_id,
                    'page': '1',
                    'num': '20',
                    'order': 'time',
                    'desc': '1',
                    'site_referer': request_url,
                    'shorturl': surl,
                    'root': '1'
                }

                async with session.get('https://www.1024tera.com/share/list', params=params) as response2:
                    response_data2 = await response2.json()
                    if 'list' not in response_data2:
                        return None

                    if response_data2['list'][0]['isdir'] == "1":
                        params.update({
                            'dir': response_data2['list'][0]['path'],
                            'order': 'asc',
                            'by': 'name',
                            'dplogid': log_id
                        })
                        params.pop('desc')
                        params.pop('root')

                        async with session.get('https://www.1024tera.com/share/list', params=params) as response3:
                            response_data3 = await response3.json()
                            if 'list' not in response_data3:
                                return None
                            return response_data3['list']
                    return response_data2['list']
    except aiohttp.ClientResponseError as e:
        print(f"Error fetching download link: {e}")
        return None


def extract_thumbnail_dimensions(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    size_param = params.get('size', [''])[0]
    if size_param:
        parts = size_param.replace('c', '').split('_u')
        if len(parts) == 2:
            return f"{parts[0]}x{parts[1]}"
    return "original"


async def get_formatted_size_async(size_bytes):
    try:
        size_bytes = int(size_bytes)
        size = size_bytes / (1024 * 1024) if size_bytes >= 1024 * 1024 else (
            size_bytes / 1024 if size_bytes >= 1024 else size_bytes
        )
        unit = "MB" if size_bytes >= 1024 * 1024 else ("KB" if size_bytes >= 1024 else "bytes")
        return f"{size:.2f} {unit}"
    except Exception as e:
        print(f"Error getting formatted size: {e}")
        return None


def transform_download_link(link: str) -> str:
    """
    Transform the direct download link from the old format (with domain d.1024tera.com)
    to the new desired format (with domain d-jp02-zen.terabox.com), adjust query params, etc.
    """
    parsed = urlparse(link)
    qs = parse_qs(parsed.query)

    # Check if the link is from the old domain
    if parsed.hostname and "1024tera.com" in parsed.hostname:
        # Replace hostname
        new_netloc = "d-jp02-zen.terabox.com"

        # For example, rename 'dstime' to 'time'
        if "dstime" in qs:
            qs["time"] = qs.pop("dstime")

        # Append new fixed parameters if they don't exist
        if "bkt" not in qs:
            qs["bkt"] = ["en-2e2b5030dd6ff037836226dff73088a02b201a20e726c575ca7a41f8c21617a854f954c0d92eb383"]
        if "xcode" not in qs:
            qs["xcode"] = ["a7b53868648021067969bda0f972f643d6f1c526452de2d367a88e4b48630e9538e20c1b34d1f923ad098f1ae8cda031b9698bea44af7e58"]

        new_query = urlencode(qs, doseq=True)
        # Construct new URL using the new domain and updated query parameters
        new_parsed = parsed._replace(netloc=new_netloc, query=new_query)
        transformed_link = urlunparse(new_parsed)
        return transformed_link

    return link


async def format_message(link_data):
    # Process thumbnails
    thumbnails = {}
    if 'thumbs' in link_data:
        for key, url in link_data['thumbs'].items():
            if url:
                dimensions = extract_thumbnail_dimensions(url)
                thumbnails[dimensions] = url
    file_name = link_data["server_filename"]
    file_size = await get_formatted_size_async(link_data["size"])
    # Transform the download link before returning
    download_link = transform_download_link(link_data["dlink"])
    sk = {
        'Title': file_name,
        'Size': file_size,
        'Direct Download Link': download_link,
        'Thumbnails': thumbnails
    }
    return sk


@app.route('/')
def hello_world():
    response = {'status': 'success', 'message': 'Working Fully', 'Contact': '@Devil_0p || @GuyXD'}
    return response


@app.route('/api', methods=['GET'])
async def Api():
    try:
        url = request.args.get('url', 'No URL Provided')
        logging.info(f"Received request for URL: {url}")
        link_data = await fetch_download_link_async(url)
        if link_data:
            tasks = [format_message(item) for item in link_data]
            formatted_message = await asyncio.gather(*tasks)
            logging.info(f"Formatted message: {formatted_message}")
        else:
            formatted_message = None
        response = {'ShortLink': url, 'Extracted Info': formatted_message, 'status': 'success'}
        return jsonify(response)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return jsonify({'status': 'error', 'message': str(e), 'Link': url})


@app.route('/help', methods=['GET'])
async def help():
    try:
        response = {
            'Info': "There is only one way to use this. Example usage:",
            'Example': 'https://server_url/api?url=https://terafileshare.com/s/1_1SzMvaPkqZ-yWokFCrKyA'
        }
        return jsonify(response)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        response = {
            'Info': "There is only one way to use this. Example usage:",
            'Example': 'https://server_url/api?url=https://terafileshare.com/s/1_1SzMvaPkqZ-yWokFCrKyA'
        }
        return jsonify(response)


if __name__ == '__main__':
    app.run(debug=True)
