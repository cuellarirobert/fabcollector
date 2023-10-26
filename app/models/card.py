# card.py
from . import db
from sqlalchemy.orm import relationship

# Represents unique cards
class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    pitch = db.Column(db.String(100), nullable=True)
    descriptor = db.Column(db.String(100))
    printings = db.relationship('Printing', back_populates='card', cascade='all, delete')





# Represents different printings of a card
class Printing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('card.id'), nullable=False)
    set_printing_unique_id = db.Column(db.String(50), nullable=False)  
    set_id = db.Column(db.String(50), nullable=False)
    edition = db.Column(db.String(20), nullable=False)
    foiling = db.Column(db.String(20), nullable=False)
    rarity = db.Column(db.String(30), nullable=False)  
    art_variation = db.Column(db.String(25), nullable=True)  
    image_url = db.Column(db.String(200), nullable=True)  
    tcgplayer_product_id = db.Column(db.String(50), nullable=True)  
    tcgplayer_url = db.Column(db.String(200), nullable=True)  
    card = db.relationship('Card', back_populates='printings')
    user_card_statuses = db.relationship('UserCardStatus', back_populates='printing')
