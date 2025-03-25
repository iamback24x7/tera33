from flask import Flask, request, jsonify
import aiohttp
import asyncio
import logging
from urllib.parse import parse_qs, urlparse

# Set up logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# NOTE: These cookies may expire. To update, log into Terabox in a browser,
# use a cookie extension like "Cookies.txt" to export cookies, and update this dictionary.
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

async def get_final_dlink(session, dlink):
    try:
        async with session.head(dlink, allow_redirects=False) as response:
            if response.status == 302:
                final_url = response.headers.get('Location', dlink)
                return final_url
            return dlink
    except Exception as e:
        logging.error(f"Error fetching final dlink for {dlink}: {e}")
        return dlink

async def fetch_download_link_async(url):
    try:
        async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
            async with session.get(url) as response1:
                response1.raise_for_status()
                response_data = await response1.text()
                js_token = find_between(response_data, 'fn%28%22', '%22%29')
                log_id = find_between(response_data, 'dp-logid=', '&')

                if not js_token or not log_id:
                    logging.error("js_token or log_id not found")
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
                        logging.error("No 'list' in response_data2")
                        return None

                    items = response_data2['list']
                    if items[0]['isdir'] == "1":
                        params.update({
                            'dir': items[0]['path'],
                            'order': 'asc',
                            'by': 'name',
                            'dplogid': log_id
                        })
                        params.pop('desc')
                        params.pop('root')

                        async with session.get('https://www.1024tera.com/share/list', params=params) as response3:
                            response_data3 = await response3.json()
                            if 'list' not in response_data3:
                                logging.error("No 'list' in response_data3")
                                return None
                            items = response_data3['list']

                    tasks = [get_final_dlink(session, item['dlink']) for item in items]
                    final_dlinks = await asyncio.gather(*tasks)
                    for item, final_dlink in zip(items, final_dlinks):
                        item['dlink'] = final_dlink

                    return items
    except Exception as e:
        logging.error(f"Error in fetch_download_link_async: {e}")
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

def get_formatted_size(size_bytes):
    try:
        size_bytes = int(size_bytes)
        if size_bytes >= 1024 * 1024:
            size = size_bytes / (1024 * 1024)
            unit = "MB"
        elif size_bytes >= 1024:
            size = size_bytes / 1024
            unit = "KB"
        else:
            size = size_bytes
            unit = "bytes"
        return f"{size:.2f} {unit}"
    except Exception as e:
        logging.error(f"Error formatting size: {e}")
        return "Unknown"

def format_message(link_data):
    thumbnails = {}
    if 'thumbs' in link_data:
        for key, url in link_data['thumbs'].items():
            if url:
                dimensions = extract_thumbnail_dimensions(url)
                thumbnails[dimensions] = url
    file_name = link_data.get("server_filename", "Unknown")
    file_size = get_formatted_size(link_data.get("size", 0))
    download_link = link_data.get("dlink", "")
    return {
        'Title': file_name,
        'Size': file_size,
        'Direct Download Link': download_link,
        'Thumbnails': thumbnails
    }

@app.route('/')
def hello_world():
    return jsonify({
        'status': 'success',
        'message': 'Working Fully',
        'Contact': '@Devil_0p || @GuyXD'
    })

@app.route('/api', methods=['GET'])
async def api():
    try:
        url = request.args.get('url', 'No URL Provided')
        logging.info(f"Received request for URL: {url}")
        link_data = await fetch_download_link_async(url)
        if link_data:
            formatted_message = [format_message(item) for item in link_data]
        else:
            formatted_message = None
        response = {
            'ShortLink': url,
            'Extracted Info': formatted_message,
            'status': 'success'
        }
        return jsonify(response)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'Link': url
        })

@app.route('/help', methods=['GET'])
def help():
    response = {
        'Info': "There is Only one Way to Use This as Show Below",
        'Example': 'https://server_url/api?url=https://terafileshare.com/s/1_1SzMvaPkqZ-yWokFCrKyA'
    }
    return jsonify(response)

if __name__ == '__main__':
    # To run with async support, use uvicorn:
    # uvicorn your_script_name:app --host 0.0.0.0 --port 5000
    app.run(debug=True)
