from flask import Flask, request, jsonify
import requests
import logging
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def parseCookieFile(cookiefile):
    cookies = {}
    with open(cookiefile, 'r') as f:
        for line in f:
            if not line.strip() or line.startswith('#'):
                continue
            name, value, domain, path, secure, expires, httponly = line.strip().split('\t')
            cookies[name] = value
    return cookies

@app.route('/api', methods=['GET'])
def api():
    try:
        url = request.args.get('url', 'No URL Provided')
        logging.info(f"Received request for URL: {url}")
        
        # Load cookies from cookies.txt (ensure this file exists and is updated)
        cookies = parseCookieFile('cookies.txt')
        
        # Extract domain and surl
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        surl = query_params.get('surl', [''])[0] if 'surl' in query_params else parsed_url.path.split('/')[-1]
        domain = parsed_url.netloc
        
        # Construct API endpoint (using terabox.com as per GitHub example)
        api_url = f'https://www.terabox.com/share/list?app_id=250528&shorturl={surl}&root=1'
        
        # Set headers
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': f'https://{domain}/sharing/link?surl={surl}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36'
        }
        
        # Make request
        response = requests.get(api_url, headers=headers, cookies=cookies)
        response.raise_for_status()
        data = response.json()
        
        # Extract download link (simplified, adjust based on actual response)
        if 'list' in data and data['list']:
            download_link = data['list'][0].get('dlink', '')
            return jsonify({
                'ShortLink': url,
                'Download Link': download_link,
                'status': 'success'
            })
        else:
            return jsonify({'status': 'error', 'message': 'No download link found'})
            
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return jsonify({'status': 'error', 'message': str(e), 'Link': url})

if __name__ == '__main__':
    app.run(debug=True)
