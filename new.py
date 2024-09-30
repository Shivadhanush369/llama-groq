import re
from urllib.parse import urlparse

def extract_urls(text: str):
    url_pattern = r'(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    urls = re.findall(url_pattern, text)
    
    formatted_urls = []
    for url in urls:
        parsed_url = urlparse(url)
        
        # If the URL starts with "www.", prepend "https://"
        if parsed_url.scheme == '' and parsed_url.netloc == '':
            url = 'https://' + url  # Assuming the URL should be treated as a domain name
        
        elif parsed_url.scheme == 'http':
            url = 'https://' + parsed_url.netloc + parsed_url.path
            
        elif parsed_url.scheme == 'https':
            url = parsed_url.geturl()
        
        formatted_urls.append(url)
    
    return formatted_urls

# Example usage:
text = " example.com for more info."
print(extract_urls(text))
