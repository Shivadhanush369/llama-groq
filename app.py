from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import logging
import re
from pymongo import MongoClient
from bson import ObjectId  # Import ObjectId to handle MongoDB IDs
from groq import Groq
from urllib.parse import urlparse
from fastapi.middleware.cors import CORSMiddleware
# Initialize FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Initialize logging
logging.basicConfig(level=logging.INFO)
 
# Model for the request body
class PromptRequest(BaseModel):
    prompt: str

class UrlRequest(BaseModel):
    text: str

class Item(BaseModel):
    id: str  # ObjectId will be serialized as string
    report: dict  # Adjust as per your document structure

# Get the API Key from environment variable
groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    raise Exception("GROQ_API_KEY is not set in environment variables.")

# Initialize Groq client
client = None
try:
    client = Groq()  # Assuming this initializes the client
except Exception as e:
    logging.error(f"Error initializing Groq client: {str(e)}")

# MongoDB configuration
mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise Exception("MONGO_URI is not set in environment variables.")
mongo_client = MongoClient(mongo_uri)
db = mongo_client["zap_dashboard"]  # Replace with your database name
collection = db["Reports"]  # Replace with your collection name

# Function to generate content using Groq
def generate_content(prompt: str):
    try:
        response = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": prompt
            }],
            model="llama-3.1-70b-versatile"
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Error generating content: {str(e)}")
        return f"An error occurred: {str(e)}"

# Function to extract URLs from text
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
            url = 'https://www.' + url  # Prepend "https://www." for domain names
        
        elif parsed_url.scheme == 'http':
            url = 'https://' + 'www.' + parsed_url.netloc + parsed_url.path
            
        elif parsed_url.scheme == 'https':
            # Always ensure "www." is present in the URL
            if not parsed_url.netloc.startswith('www.'):
                url = 'https://www.' + parsed_url.netloc + parsed_url.path
        url = url +"/"    
        formatted_urls.append(url)

    return formatted_urls

# Example usage:
text = "Visit example.com for more info."
print(extract_urls(text))



# Utility function to serialize MongoDB documents
def serialize_mongo_doc(doc):
    """Convert MongoDB document to JSON serializable dict."""
    if isinstance(doc, list):
        return [serialize_mongo_doc(item) for item in doc]
    if isinstance(doc, dict):
        return {k: str(v) if isinstance(v, ObjectId) else v for k, v in doc.items()}
    return doc

# API endpoint to generate content
#@app.post("/generate")
def generate(prompt,dbresult):
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    
     
    # Combine the dbresult and the new prompt with the specified text
    combined_prompt = dbresult + "\n"+prompt + " and don't use phrases like according to the provided info" + "and i want response should be prettified and short"
    

    output = generate_content(combined_prompt)
    
    if "An error occurred" in output:
        raise HTTPException(status_code=500, detail=output)
    
    return {"content": output}

# API endpoint to extract URLs and fetch records from MongoDB
@app.post("/fetch_records", response_model=dict)  # Adjust response model if needed
async def fetch_records(request: UrlRequest):
    if not request.text:
        raise HTTPException(status_code=400, detail="Text is required")
    
    urls = extract_urls(request.text)
    print(urls)
    if not urls:
        raise HTTPException(status_code=404, detail="No URLs found in the text.")
    
    logging.info(f"Extracted URLs: {urls}")
    records = []
    for url in urls:
        # Query MongoDB for records with the extracted URL
        found_records = list(collection.find({"report.url.url": url}))  # Use the extracted URL
        records.extend(serialize_mongo_doc(found_records))
        results = extract_report({"records": records})

    response = generate(request.text,results)
    if not records:
        raise HTTPException(status_code=404, detail="No records found for the extracted URLs")
    
    return {"response": response}

def extract_report(details):
    data = details.get("records", [])
    report_str = ""

    for index, report_entry in enumerate(data):
        scan_number = index
        print(f"Iteration {index}")
        SiteInfo = report_entry['report'].get('site', [])

        # Check if SiteInfo is empty or None
        if not SiteInfo or len(SiteInfo) == 0:
            site_name = host = port = ssl = 0
            report_str += f"Site Information:\n scan_number:{scan_number+1} Site: {site_name}\n  Host: {host}\n  Port: {port}\n  SSL: {ssl}\n"
            report_str += "\nVulnerabilities:\n  No vulnerabilities found.\n"
            report_str += "\n" + "-" * 50 + "\n\n"
            continue
        
        site_info = SiteInfo[0]

        site_name = site_info.get('@name', 0)
        host = site_info.get('@host', 0)
        port = site_info.get('@port', 0)
        ssl = site_info.get('@ssl', 0)

        # Append site information for each report entry
        report_str += f"Site Information:\n scan_number:{scan_number+1} Site: {site_name}\n  Host: {host}\n  Port: {port}\n  SSL: {ssl}\n"
        report_str += "\nVulnerabilities:\n"

        for idx, alert in enumerate(site_info.get('alerts', []), 1):
            alert_name = alert.get('alert', 'Unknown Alert')
            risk_level = alert.get('riskdesc', 'Unknown Risk').split(' ')[0]
            description = alert.get('desc', 'No description available.').replace('<p>', '').replace('</p>', '')
            solution = alert.get('solution', 'No solution provided.').replace('<p>', '').replace('</p>', '')

            report_str += f"{idx}. **{alert_name}**:\n"
            report_str += f"   Risk Level: {risk_level}\n"
            report_str += f"   Description: {description}\n"

            if 'instances' in alert and alert['instances']:
                report_str += "   Instances:\n"
                for instance in alert['instances']:
                    report_str += f"   - {instance.get('uri', 'No URI provided.')}\n"

            report_str += f"   Solution: {solution}\n\n"

        # Append a new line to separate each report entry
        report_str += "\n" + "-" * 50 + "\n\n"

    return report_str




