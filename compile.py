#!/usr/env/bin/python3
from google import genai

prompt = "List some websites about landmarks, historical figures, and \
      narratives specifically related to Philadelphia and Pennsylvania,\
          with a focus on celebrating the US's 250th anniversary. Do not\
              provide any additional explanation. Print each link on one \
                line wihtout using any additional character as bullet points."

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

response = client.models.generate_content(
    model="gemini-3-flash-preview", contents=prompt
)

with open("websites.txt", "w") as out:
    out.write(response.text)