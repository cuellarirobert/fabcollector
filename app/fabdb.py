# app/fabdb.py

from flask import render_template
from .models.card import Card, Printing
from .models.user_card_status import UserCardStatus
import requests

def show_decklist(slug):
    api_url = f'https://api.fabdb.net/decks/{slug}'

    try:
        response = requests.get(api_url)

        if response.status_code == 200:
            deck_data = response.json()
            return deck_data

        else:
            return f"Failed to fetch decklist. Status code: {response.status_code}", 500

    except requests.RequestException as e:
        return f"Error fetching decklist: {str(e)}", 500


