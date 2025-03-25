from flask import Flask, request, jsonify
import aiohttp
import asyncio
import logging
from urllib.parse import parse_qs, urlparse

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Updated cookies and headers
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
    return string[start_index:end_index] if start_index >= len(start) and end_index != -1 else ''

def extract_thumbnail_dimensions(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    size_param = params.get('size', [''])[0]
    if size_param:
        parts = size_param.replace('c', '').split('_u')
        return f"{parts[0]}x{parts[1]}" if len(parts) == 2 else "original"
    return "original"

async def get_formatted_size_async(size_bytes):
    try:
        size_bytes = int(size_bytes)
        if size_bytes >= 1024 * 1024 * 1024:
            size = size_bytes / (1024 * 1024 * 1024)
            unit = "GB"
        elif size_bytes >= 1024 * 1024:
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
        logging.error(f"Size formatting error: {e}")
        return "Unknown size"

async def resolve_final_url(session, dlink):
    try:
        async with session.get(dlink, allow_redirects=True) as response:
            return str(response.url)
    except Exception as e:
        logging.error(f"URL resolution failed: {e}")
        return dlink

async def process_file_list(session, file_list):
    processed_files = []
    for file in file_list:
        if file.get('isdir') == "1":
            continue
            
        final_url = await resolve_final_url(session, file['dlink'])
        thumbs = {
            extract_thumbnail_dimensions(url): url
            for key, url in file.get('thumbs', {}).items()
            if url
        }
        
        processed_files.append({
            'filename': file['server_filename'],
            'size': await get_formatted_size_async(file['size']),
            'url': final_url,
            'thumbnails': thumbs,
            'category': file.get('category', 'Unknown'),
            'md5': file.get('md5', '')
        })
    return processed_files

async def fetch_share_data(session, url):
    try:
        async with session.get(url) as response:
            text = await response.text()
            js_token = find_between(text, 'fn%28%22', '%22%29')
            log_id = find_between(text, 'dp-logid=', '&')
            
            if not js_token or not log_id:
                return None

            surl = str(response.url).split('surl=')[1]
            return {
                'js_token': js_token,
                'log_id': log_id,
                'surl': surl,
                'referer': str(response.url)
            }
    except Exception as e:
        logging.error(f"Initial fetch failed: {e}")
        return None

async def handle_directory(session, params, path):
    dir_params = params.copy()
    dir_params.update({
        'dir': path,
        'order': 'asc',
        'by': 'name',
        'page': '1',
        'num': '1000'
    })
    dir_params.pop('desc', None)
    dir_params.pop('root', None)
    
    async with session.get('https://www.1024tera.com/share/list', params=dir_params) as response:
        data = await response.json()
        return await process_file_list(session, data.get('list', []))

async def fetch_download_link_async(url):
    try:
        async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
            share_data = await fetch_share_data(session, url)
            if not share_data:
                return None

            params = {
                'app_id': '250528',
                'web': '1',
                'channel': 'dubox',
                'clienttype': '0',
                'jsToken': share_data['js_token'],
                'dplogid': share_data['log_id'],
                'page': '1',
                'num': '1000',
                'order': 'time',
                'desc': '1',
                'site_referer': share_data['referer'],
                'shorturl': share_data['surl'],
                'root': '1'
            }

            async with session.get('https://www.1024tera.com/share/list', params=params) as response:
                data = await response.json()
                file_list = data.get('list', [])
                
                if not file_list:
                    return None

                if file_list[0].get('isdir') == "1":
                    return await handle_directory(session, params, file_list[0]['path'])
                
                return await process_file_list(session, file_list)
    except Exception as e:
        logging.error(f"Main fetch error: {e}")
        return None

@app.route('/')
def home():
    return jsonify({
        'status': 'active',
        'message': 'Terabox Direct Link API',
        'documentation': 'Use /api?url=YOUR_TERABOX_SHARE_URL'
    })

@app.route('/api', methods=['GET'])
async def api_endpoint():
    try:
        share_url = request.args.get('url')
        if not share_url:
            return jsonify({'error': 'Missing URL parameter'}), 400
        
        result = await fetch_download_link_async(share_url)
        if not result:
            return jsonify({'error': 'No files found or invalid URL'}), 404
        
        return jsonify({
            'status': 'success',
            'source_url': share_url,
            'file_count': len(result),
            'files': result
        })
    except Exception as e:
        logging.error(f"API Error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Internal server error',
            'debug': str(e)
        }), 500

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': int(time.time())})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
