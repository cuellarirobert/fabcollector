from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response, Response
from flask_session import Session
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash
from .models import db
from .models.card import Card, Printing
from .models.user import User
from .models.user_card_status import UserCardStatus
import sys
import os
import requests
from functools import wraps
from sqlalchemy import func, join
from collections import defaultdict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects import postgresql
import json
import pandas as pd
from io import StringIO
import csv
import hashlib
from .fabdb import show_decklist

current_dir = os.path.dirname(os.path.abspath(__file__))
models_dir = os.path.join(current_dir, 'models')

login_manager = LoginManager()

json_file_path = os.path.join(current_dir, 'static', 'json', 'cards.json')

sys.path.append(models_dir)

# use to make sure the database source (the json file is up to date)
def compute_checksum(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def convert_pitch(pitch_str):
    if pitch_str == 'red':
        return 1
    elif pitch_str == 'yellow':
        return 2
    elif pitch_str == 'blue':
        return 3
    else:
        return None

def parse_deck(deck_str):
    lines = deck_str.strip().split('\n')
    hero = ''
    weapons = []
    equipment = []
    cards = defaultdict(int)
    last_pitch = None
    
    for line in lines:
        if 'Class:' in line:
            continue
        elif 'Hero:' in line:
            hero = line.split('Hero:', 1)[1].strip()
        elif 'Weapons:' in line:
            weapons = line.split('Weapons:', 1)[1].strip().split(', ')
        elif 'Equipment:' in line:
            equipment = line.split('Equipment:', 1)[1].strip().split(', ')
        elif line.startswith('('):
            count, card_info = line[1:].split(')', 1)
            card_parts = card_info.strip().rsplit(' ', 1)
            name = card_parts[0].strip()
            
            pitch = None

            if len(card_parts) > 1:
                last_word = card_parts[-1][1:-1]
                if last_word in ['red', 'yellow', 'blue']:
                    pitch = convert_pitch(last_word)
                else:
                    name = card_info.strip()
            
            if pitch is None:
                pitch = last_pitch
            
            last_pitch = pitch
            
            cards[(name, pitch)] += int(count)

    deck_dict = {
        'hero': hero,
        'weapons': weapons,
        'equipment': equipment,
        'cards': cards
    }
    return deck_dict



def fetch_printings_info(card, count, user_id):
    printings = Printing.query.filter_by(card_id=card.id).all()
    printing_info = []
    for printing in printings:
        user_card_status = UserCardStatus.query.filter_by(user_id=user_id, printing_id=printing.id).first()
        owned_quantity = user_card_status.amount if user_card_status else 0
        printing_info.append({
            'set_id': printing.set_id,
            'edition': printing.edition,
            'foiling': printing.foiling,
            'art_variation': printing.art_variation,
            'rarity': printing.rarity,
            'owned_quantity': owned_quantity,
            'number_in_deck': count
        })
    return printing_info

def prepare_card_data(card, count, user_id):
    return {
        'name': card.name,
        'pitch': card.pitch,
        'descriptor': card.descriptor,
        'printings_info': fetch_printings_info(card, count, user_id),
        'amount': count
    }

def process_cards(cards, counts, user_id):
    card_data = []
    for card in cards:
        card_data.append(prepare_card_data(card, counts.count(card.name), user_id))
    return card_data

def update_user_card_status(user_id, printing_id, value, status="owned"):
    try:
        user_card_statuses = UserCardStatus.query.filter_by(user_id=user_id, printing_id=printing_id).first()
        if user_card_statuses:
            if user_card_statuses.amount != value:
                user_card_statuses.amount = value
                return True, f"{printing.card.name}: {value}"
        else:
            new_status = UserCardStatus(user_id=user_id, printing_id=printing_id, amount=value, status=status)
            db.session.add(new_status)
            return True, f"{printing.card.name}: {value}"
    except SQLAlchemyError as e:
        print(f"SQLAlchemyError when adding/updating status: {e}")
        return False, None


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///newfabsite.db'
    app.secret_key = 'fawkfj2309j9023j90j099aj90ecaewja0wej90J9j09j09j109j1w09j09j90jx190j120a12'
    db.init_app(app)

    login_manager.init_app(app)


    checksum_file_path = 'checksum.txt'

    with app.app_context():
        db.create_all()

        if os.path.exists(checksum_file_path):
            with open(checksum_file_path, 'r') as f:
                stored_checksum = f.read().strip()
        else:
            stored_checksum = None

        current_checksum = compute_checksum(json_file_path)

        if stored_checksum != current_checksum or Card.query.count() == 0:
            with open(json_file_path, 'r') as f:
                data = json.load(f)

            df_cards = pd.DataFrame(data)
            unique_id_to_card_id = {}

            for _, row in df_cards.iterrows():
                name_parts = row['name'].split(", ")
                name = name_parts[0].strip()
                descriptor = name_parts[1].strip() if len(name_parts) > 1 else None

                new_card = Card(
                    unique_id=row['unique_id'],
                    name=row['name'],
                    descriptor=descriptor,
                    pitch=row.get('pitch', None)
                )
                db.session.add(new_card)
                db.session.flush()
                unique_id_to_card_id[row['unique_id']] = new_card.id

            db.session.commit()

            for record in data:
                card_unique_id = record['unique_id']
                card_id = unique_id_to_card_id.get(card_unique_id)
                if card_id is not None:
                    for printing in record.get('printings', []):
                        new_printing = Printing(
                            card_id=card_id,
                            set_printing_unique_id=printing['set_printing_unique_id'],
                            set_id=printing['id'],
                            edition=printing['edition'],
                            foiling=printing['foiling'],
                            rarity=printing['rarity'],
                            art_variation=printing.get('art_variation', None)
                        )
                        db.session.add(new_printing)

            db.session.commit()

            with open(checksum_file_path, 'w') as f:
                f.write(current_checksum)

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return render_template('collection.html')
        else:
            return redirect(url_for('login'))


    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            
            user = User.query.filter_by(username=username).first()
            
            if user is None or not check_password_hash(user.password, password):
                return "invalid username and/or password", 403
            
            login_user(user)
            return redirect(url_for("index"))
        else:
            return render_template("login.html")


    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @app.route('/fabraryTable', methods=['POST'])
    def fabraryTable():
        if request.method == 'POST':
            deck_str = request.form.get('decklist')
            
            deck_data = parse_deck(deck_str)
            hero = deck_data['hero']
            weapons = deck_data['weapons']
            equipment = deck_data['equipment']
            cards_data = deck_data['cards']

            weapon_cards = []
            equipment_cards = []
            other_cards = []

            descriptor_to_name = {}
            for card in Card.query.filter(Card.descriptor.isnot(None)).all():
                descriptor_to_name[card.descriptor] = card.name

            for i, weapon in enumerate(weapons):
                if weapon in descriptor_to_name:
                    weapons[i] = descriptor_to_name[weapon]

            for i, equip in enumerate(equipment):
                if equip in descriptor_to_name:
                    equipment[i] = descriptor_to_name[equip]

            weapon_cards = Card.query.filter(Card.name.in_(weapons)).all()
            equipment_cards = Card.query.filter(Card.name.in_(equipment)).all()

            for card in weapon_cards:
                card.printings_info = Printing.query.filter_by(card_id=card.id).all()
            
            for card in equipment_cards:
                card.printings_info = Printing.query.filter_by(card_id=card.id).all()

            for (card_name, pitch), count in cards_data.items():
                card = Card.query.filter_by(name=card_name, pitch=pitch).first()
                if card:
                    printings = Printing.query.filter_by(card_id=card.id).all()
                    printing_info = []
                    for printing in printings:
                        user_card_status = UserCardStatus.query.filter_by(user_id=current_user.id, printing_id=printing.id).first()
                        owned_quantity = user_card_status.amount if user_card_status else 0
                        needed_quantity = count - owned_quantity
                        pitch = card.pitch

                        printing_info.append({
                            'set_id': printing.set_id,
                            'edition': printing.edition,
                            'foiling': printing.foiling,
                            'art_variation': printing.art_variation,
                            'rarity': printing.rarity,
                            'pitch': pitch,
                            'owned_quantity': owned_quantity,
                            'needed_quantity': needed_quantity,
                        })

                    card_data = {
                        'name': card.name,
                        'pitch': card.pitch,
                        'descriptor': card.descriptor,
                        'printings_info': printing_info,
                        'amount': count
                    }

                    other_cards.extend([card_data] * count)
                else:
                    card_name_with_pitch = f"{card_name} (Pitch: {pitch})"
                    print(f"Invalid Card: {card_name_with_pitch}")
                    print(f"Card Data: {cards_data[(card_name, pitch)]}")
                    pass

            response_data = {
                "hero": hero,
                "weapon_cards": weapon_cards,
                "equipment_cards": equipment_cards,
                "other_cards": other_cards,
            }

            return render_template('table_template.html', response_data=response_data)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username")
            email = request.form.get("email")
            password = request.form.get("password")
            password_again = request.form.get("password_again")
            
            if password != password_again:
                return "passwords do not match"
            
            existing_user = User.query.filter_by(username=username).first()
            existing_email = User.query.filter_by(email=email).first()
            
            if existing_user is None:
                hashed_password = generate_password_hash(password)
                new_user = User(username=username, email=email, password=hashed_password)
                db.session.add(new_user)
                db.session.commit()
                return redirect(url_for("login"))

        return render_template("register.html")

    @app.route('/getTable', methods=['POST', 'GET'])
    def get_table():
        slug = request.form.get('slug')
        user_id = session.get("_user_id")
        current_user.id = user_id if user_id else None

        original_deck_data = show_decklist(slug)
        if 'error' in original_deck_data:
            return jsonify({'error': original_deck_data['error']})

        equipment_cards = []
        hero_cards = []
        weapon_cards = []
        other_cards = []

        for card in original_deck_data['cards']:
            set_id = card['printings'][0]['sku']['set']['id'].upper() + str(card['printings'][0]['sku']['number'])
            print(f"Constructed set_id: {set_id}")
            related_printing = Printing.query.filter_by(set_id=set_id).first()

            if related_printing:
                print(f"Found related printing with card_id: {related_printing.card_id}")
            else:
                print("No related printing found.")
            if related_printing:
                card_id = related_printing.card_id
                print(card_id)
            else:
                card_id = None
            card_printings_info = []

            if related_printing:
                printings = Printing.query.filter_by(card_id=card_id).all()
                for printing in printings:
                    related_card = Card.query.filter_by(id=printing.card_id).first()
                    user_card_status = UserCardStatus.query.filter_by(user_id=current_user.id, printing_id=printing.id).first()
                    owned_quantity = user_card_status.amount if user_card_status else 0
                    needed_quantity = card['total'] - owned_quantity

                    card_printings_info.append({
                        'set_id': printing.set_id,
                        'edition': printing.edition,
                        'foiling': printing.foiling,
                        'art_variation': printing.art_variation,
                        'rarity': printing.rarity,
                        'number_in_deck': card['total'],
                        'owned_quantity': owned_quantity,
                        'needed_quantity': needed_quantity,
                        'pitch': related_card.pitch if related_card else None
                    })
                

            if card["type"] == "equipment":
                equipment_card_data = {
                "amount": card.get("total", 1),  
                "descriptor": card.get("descriptor", None),  
                "name": card.get("name", ""),
                "printings_info": card_printings_info
                }
                equipment_cards.append(equipment_card_data)
            elif card["type"] == "hero":
                hero_card_data = {
                "amount": card.get("total", 1),  
                "descriptor": card.get("descriptor", None),  
                "name": card.get("name", ""),
                "printings_info": card_printings_info
                }
                hero_cards.append(hero_card_data)
            elif card["type"] == "weapon":
                weapon_card_data = {
                "amount": card.get("total", 1),
                "descriptor": card.get("descriptor", None),
                "name": card.get("name", ""),
                "printings_info": card_printings_info
                }
                weapon_cards.append(weapon_card_data)
            else:
                other_card_data = {
                "amount": card.get("total", 1),
                "descriptor": card.get("descriptor", None),
                "name": card.get("name", ""),
                "printings_info": card_printings_info
                }
                other_cards.append(other_card_data)


        new_deck_data = {
            "equipment_cards": equipment_cards,
            "hero_cards": hero_cards,
            "weapon_cards": weapon_cards,
            "other_cards": other_cards,
        }

        session['response_data'] = {
                "user_id": user_id,
                "hero": hero_cards[0]["name"],
                "weapon_cards": weapon_cards,
                "equipment_cards": equipment_cards,
                "other_cards": other_cards,
            }
        session['filters'] = {}
        return redirect(url_for('deck_table'))

    @app.route('/importDeck')
    def importDeck():
        user_id = session.get("_user_id")
        current_user.id = user_id if user_id else None
        return render_template("importDeck.html")


    @app.route('/decklist/update-owned', methods=['POST'])
    def update_db_owned():
        user_id = session.get("_user_id")
        if not user_id:
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

        form_data = request.form

        changes_made = False
        updated_cards = []

        for key, value in form_data.items():
            if "owned_cards__" in key:
                parts = key.split("__")[1].split("_")
                if len(parts) != 4:
                    continue
                printing, edition, foiling, art_variation = parts
                if art_variation == 'None':
                    art_variation = None
                
                try:
                    value = int(value)
                except ValueError:
                    continue

                try:
                    if art_variation is None:
                        query = Printing.query.filter_by(set_id=printing, edition=edition, foiling=foiling).filter(Printing.art_variation.is_(None))
                    else:
                        query = Printing.query.filter_by(set_id=printing, edition=edition, foiling=foiling, art_variation=art_variation)
                    
                    print(query.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

                    printings = query.first()
                except SQLAlchemyError as e:
                    print(f"SQLAlchemyError when querying printings: {e}")
                    continue
                
                if not printings:
                    continue

                try:
                    user_card_statuses = UserCardStatus.query.filter_by(user_id=user_id, printing_id=printings.id).first()
                except SQLAlchemyError as e:
                    print(f"SQLAlchemyError when querying user_card_statuses: {e}")
                    continue

                if user_card_statuses:
                    if user_card_statuses.amount != value:
                        user_card_statuses.amount = value
                        updated_cards.append(f"{printings.card.name}: {value}")
                        changes_made = True
                else:
                    try:
                        new_status = UserCardStatus(user_id=user_id, printing_id=printings.id, amount=value, status="owned")
                        db.session.add(new_status)
                        updated_cards.append(f"{printings.card.name}: {value}")
                        changes_made = True
                    except SQLAlchemyError as e:
                        print(f"SQLAlchemyError when adding new status: {e}")
                        continue

        if changes_made:
            try:
                db.session.commit()
                return make_response(jsonify({'status': 'success', 'message': 'Card ownership successfully updated.'}), 200)
            except SQLAlchemyError as e:
                db.session.rollback()
                print(f"SQLAlchemyError when committing to the database: {e}")
                return jsonify({'status': 'error', 'message': f'Database error: {e}'}), 500
        else:
            return jsonify({'status': 'error', 'message': 'No updates made'}), 400 

    @app.route('/decklist/fabrary-update-owned', methods=['POST'])
    def fabrary_update_owned():
        user_id = session.get("_user_id")
        if not user_id:
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

        try:
            changes_made = False
            updated_cards = []
            form_data = request.form

            for key, value in form_data.items():
                if key.startswith("owned_cards_"):
                    card_id = key.split("_")[-1]
                    set_id = form_data.get(f"data-set-id_{card_id}")
                    edition = form_data.get(f"data-edition_{card_id}")
                    foiling = form_data.get(f"data-foiling_{card_id}")
                    art_variation = form_data.get(f"data-art-variation_{card_id}")
                    rarity = form_data.get(f"data-rarity_{card_id}")

                    print(set_id, edition, foiling, art_variation, rarity)
                    print(int(value))

                    try:
                        value = int(value)
                    except ValueError:
                        continue

                    printings = Printing.query.filter_by(set_id=set_id, edition=edition, foiling=foiling, art_variation=art_variation).first()
                    if printings:
                        card_name = printings.card.name  
                        first_printing_id = printings.id
                        user_card_statuses = UserCardStatus.query.filter_by(
                            user_id=user_id, printing_id=first_printing_id
                        ).first()

                        if user_card_statuses:
                            if user_card_statuses.amount != value:
                                user_card_statuses.amount = value
                                updated_cards.append(f"{card_name}: {value}")
                                changes_made = True

                        else:
                            new_status = UserCardStatus(
                                user_id=user_id,
                                printing_id=first_printing_id,
                                amount=value,
                                status="owned"
                            )
                            db.session.add(new_status)
                            updated_cards.append(f"{card_name}: {value}")
                            changes_made = True

            if changes_made:
                db.session.commit()
                return jsonify({'status': 'success', 'message': 'Card ownership successfully updated.'}), 200
            else:
                return jsonify({'status': 'no_changes', 'message': 'No changes were made.'}), 200

        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': f'An error occurred: {e}'}), 500

    @app.route('/collection')
    def collection():
        user_id = session.get("_user_id")
        if not user_id:
            return "Unauthorized", 401
        return render_template('collection.html')


    @app.route('/collection_table')
    def collection_table():
        user_id = session.get("_user_id")
        if not user_id:
            return "Unauthorized", 401

        edition = request.args.get('edition')
        rarity = request.args.get('rarity')
        foiling = request.args.get('foiling')
        art_variation = request.args.get('artVariation')

        query = UserCardStatus.query.filter_by(user_id=user_id)

        query = query.filter(UserCardStatus.amount > 0)

        if edition and edition != 'all':
            query = query.filter(UserCardStatus.printing.has(edition=edition))
        if rarity and rarity != 'all':
            query = query.filter(UserCardStatus.printing.has(rarity=rarity))
        if foiling and foiling != 'all':
            query = query.filter(UserCardStatus.printing.has(foiling=foiling))
        if art_variation and art_variation != 'all':
            query = query.filter(UserCardStatus.printing.has(art_variation=art_variation))


        user_card_statuses = query.all()
        print(user_card_statuses)

        cards = []
        for status in user_card_statuses:
            printing = status.printing
            card = printing.card
            cards.append({
                'card_name': card.name,
                'printing_id': printing.id,
                'set_id': printing.set_id,
                'edition': printing.edition,
                'foiling': printing.foiling,
                'art_variation': printing.art_variation,
                'rarity': printing.rarity,
                'amount': status.amount
            })

        return render_template('collection_table.html', cards=cards)


    def get_filtered_cards():
        user_id = session.get("_user_id")
        if not user_id:
            return "Unauthorized", 401

        edition = request.args.get('edition')
        rarity = request.args.get('rarity')
        foiling = request.args.get('foiling')
        art_variation = request.args.get('artVariation')

        query = (db.session.query(UserCardStatus, Card, Printing)
                 .join(Card, Card.id == Printing.card_id)
                 .join(Printing, Printing.id == UserCardStatus.printing_id)
                 .filter(UserCardStatus.user_id == user_id))

        if edition and edition != 'all':
            query = query.filter(Printing.edition == edition)
        if rarity and rarity != 'all':
            query = query.filter(Printing.rarity == rarity)
        if foiling and foiling != 'all':
            query = query.filter(Printing.foiling == foiling)
        if art_variation and art_variation != 'all':
            query = query.filter(UserCardStatus.printing.has(art_variation=art_variation))

        cards = query.all()
        return cards

    @app.route('/prepareCustomTable', methods=['POST'])
    def prepare_custom_table():
        if request.method == 'POST':
            user_id = session.get("_user_id")
            deck_str = request.form.get('decklist')
            deck_data = parse_deck(deck_str)
            
            descriptor_to_name = {card.descriptor: card.name for card in Card.query.filter(Card.descriptor.isnot(None)).all()}

            hero = deck_data['hero']
            weapons = [descriptor_to_name.get(weapon, weapon) for weapon in deck_data['weapons']]
            equipment = [descriptor_to_name.get(equip, equip) for equip in deck_data['equipment']]
            cards_data = deck_data['cards']

            weapon_cards = Card.query.filter(Card.name.in_(weapons)).all()
            equipment_cards = Card.query.filter(Card.name.in_(equipment)).all()
            other_cards = [Card.query.filter_by(name=card_name, pitch=pitch).first() for (card_name, pitch), count in cards_data.items()]

            weapon_cards_data = process_cards(weapon_cards, weapons, user_id)
            equipment_cards_data = process_cards(equipment_cards, equipment, user_id)
            other_cards_data = [prepare_card_data(card, count, user_id) for card, count in zip(other_cards, cards_data.values()) if card]

            session['response_data'] = {
                "user_id": user_id,
                "hero": hero,
                "weapon_cards": weapon_cards_data,
                "equipment_cards": equipment_cards_data,
                "other_cards": other_cards_data,
            }
            print(session['response_data'])
            session['filters'] = {}
            return redirect(url_for('deck_table'))

    @app.route('/decklist_table')
    def decklist_table():
        user_id = session.get("_user_id")
        if not user_id:
            return "Unauthorized", 401

        filters = session.get('filters', {})

        print(f"these are my historical filters: {filters}")

        for key in ['edition', 'rarity', 'foiling', 'artVariation']:
            value = request.args.get(key)
            if value:
                filters[key] = value
                print(f"Updated filters: {filters}")

        session['filters'] = filters
        print(f"latest filters: {filters}")

        deck_data = session.get('response_data', {})

        cards = []
        for card_type in ['weapon_cards', 'equipment_cards', 'other_cards']:
            for card_info in deck_data.get(card_type, []):
                for printing_info in card_info.get('printings_info', []):
                    should_append = True 

                    if filters.get('edition', 'all') != 'all' and printing_info['edition'] != filters['edition']:
                        should_append = False
                    if filters.get('rarity', 'all') != 'all' and printing_info['rarity'] != filters['rarity']:
                        should_append = False
                    if filters.get('foiling', 'all') != 'all' and printing_info['foiling'] != filters['foiling']:
                        should_append = False
                    if filters.get('artVariation', 'all') != 'all' and (not printing_info.get('art_variation') or printing_info['art_variation'] != filters['artVariation']):
                        should_append = False

                    if should_append:
                        card_name = card_info['name']
                        set_id = printing_info['set_id']
                        owned_quantity = printing_info.get('owned_quantity', 0)
                        number_in_deck = printing_info.get('number_in_deck', 0)
                        net_needed_quantity = number_in_deck - owned_quantity

                        pitch = printing_info.get('pitch', card_info.get('pitch', '0'))

                        cards.append({
                            'card_name': card_name,
                            'set_id': set_id,
                            'pitch': pitch,
                            'edition': printing_info['edition'],
                            'foiling': printing_info['foiling'],
                            'art_variation': printing_info['art_variation'],
                            'rarity': printing_info['rarity'],
                            'number_in_deck': printing_info['number_in_deck'],
                            'owned_quantity': owned_quantity,
                            'needed': net_needed_quantity
                        })

        return render_template('decklist_table.html', cards=cards)

    @app.route('/export_csv')
    def export_csv():
        user_id = session.get("_user_id")
        if not user_id:
            return "Unauthorized", 401

        query = UserCardStatus.query.filter_by(user_id=user_id)
        query = query.filter(UserCardStatus.amount > 0)
        user_card_statuses = query.all()

        pitch_mapping = {
            "1": "Red",
            "2": "Yellow",
            "3": "Blue",
            None: "None"
        }
        set_mapping = {
            "1HP": "History Pack 1",
            "ARA": "Arakni Blitz Deck",
            "ARC": "Arcane Rising",
            "AZL": "Azalea Blitz Deck",
            "BEN": "Benji Blitz Deck",
            "BOL": "Boltyn Blitz Deck",
            "BRI": "Briar Blitz Deck",
            "BVO": "Bravo Hero Deck",
            "CHN": "Chane Blitz Deck",
            "CRU": "Crucible of War",
            "DRO": "Dromai Blitz Deck",
            "DTD": "Dusk till Dawn",
            "DVR": "Classic Battles: Rhinar vs Dorinthea – Dorinthea",
            "DYN": "Dynasty",
            "ELE": "Tales of Aria",
            "EVO": "Bright Lights",
            "EVR": "Everfest",
            "FAB": "Promos",
            "FAI": "Fai Blitz Deck",
            "HER": "Hero Card Promos",
            "IRA": "Ira Welcome Deck",
            "JDG": "Judge Unique Promos",
            "KAT": "Katsu Blitz Deck",
            "KSU": "Katsu Hero Deck",
            "LEV": "Levia Blitz Deck",
            "LGS": "Local Game Store Promos",
            "LSS": "LSS Promos",
            "LXI": "Lexi Blitz Deck",
            "MON": "Monarch",
            "OLD": "Oldhim Blitz Deck",
            "OUT": "Outsiders",
            "OXO": "Slingshot Underground Promos",
            "PSM": "Prism Blitz Deck",
            "RIP": "Riptide Blitz Deck",
            "RNR": "Rhinar Hero Deck",
            "RVD": "Classic Battles: Rhinar vs Dorinthea – Rhinar",
            "TCC": "Round the Table: TCC X LSS",
            "TEA": "Dorinthea Hero Deck",
            "UPR": "Uprising",
            "UZU": "Uzuri Blitz Deck",
            "WIN": "Worlds / Pro Tour Prize Cards",
            "WTR": "Welcome to Rathe",
            "XXX": "OP Event Tokens"
        }
        rarity_mapping = {
            "C": "Common",
            "R": "Rare",
            "S": "Super Rare",
            "M": "Majestic",
            "L": "Legendary",
            "F": "Fabled",
            "T": "Token",
            "V": "Marvel",
            "P": "Promo"
        }
        art_variation_mapping = {
            "AB": "Alternate Border",
            "AA": "Alternate Art",
            "AT": "Alternate Text",
            "EA": "Extended Art",
            "FA": "Full Art"
        }

        foiling_mapping = {
            "S": "Standard",
            "R": "Rainbow Foil",
            "C": "Cold Foil",
            "G": "Gold Cold Foil"
        }

        edition_mapping = {
            "A": "Alpha",
            "F": "First",
            "U": "Unlimited",
            "N": "N/A"
        }

        output = StringIO()
        csv_writer = csv.writer(output)

        csv_writer.writerow(['Identifier', 'Name', 'Pitch', 'Set', 'Set number', 'Edition', 'Foiling', 'Art Variation', 'Rarity'])

        for status in user_card_statuses:
            printing = status.printing
            card = printing.card

            identifier = card.name.replace(" ", "-").replace(",", "-").lower()
            name = card.name
            pitch = pitch_mapping.get(card.pitch, 'Unknown')
            set_prefix = printing.set_id[:3]
            set_name = set_mapping.get(set_prefix, 'Unknown')
            set_number = printing.set_id[-3:]
            edition = edition_mapping.get(printing.edition, 'Unknown')
            foiling = foiling_mapping.get(printing.foiling, 'Unknown')
            art_variation = art_variation_mapping.get(printing.art_variation, 'Unknown')
            rarity = rarity_mapping.get(printing.rarity, 'Unknown')
            csv_writer.writerow([identifier, name, pitch, set_name, set_number, edition, foiling, art_variation, rarity])

        output.seek(0)

        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=collection.csv"}
        )



    @app.route('/deck_table')
    def deck_table():
        return render_template('decklist.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
