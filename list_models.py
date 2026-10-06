from google import genai
client = genai.Client(api_key='AIzaSyDlWM2_lrP-x-GP2wQrgmLL76Ouz9w7How')
for model in client.models.list():
    if 'generateContent' in model.supported_actions:
        print(model.name)
