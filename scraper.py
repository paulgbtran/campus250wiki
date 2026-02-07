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

def scrape(link):
    pass


def main():
    pass

if __name__ == '__main__':
    main()