# user_card_status.py
from . import db

class UserCardStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    printing_id = db.Column(db.Integer, db.ForeignKey('printing.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False)
    user = db.relationship('User', back_populates='user_card_statuses')
    printing = db.relationship('Printing', back_populates='user_card_statuses')
