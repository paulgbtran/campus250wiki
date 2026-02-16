#!/usr/env/bin/python3
import requests
from bs4 import BeautifulSoup

def readPages(): 
    with open('websites.txt', 'r') as inp:
        websites = inp.readlines()
    
    for link in websites:
        if '\n' in link:
            link.replace('\n', '')
    
    return websites

def scrape():
    with open('websites.txt', 'r') as inp:
        websites = inp.readlines()

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}


        for link in websites:
            try:
                response = requests.get(link)
                soup = BeautifulSoup(response.text, 'html.parser')
                print(soup.title) 
            except:
                print(f'Error retrieving {link}. Status code {response.status_code}')   


def main():
    scrape()

if __name__ == '__main__':
    main()