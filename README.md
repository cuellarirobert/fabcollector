<<<<<<< HEAD
# fabdeckcollector
FaB Collection Management tool using Fabdb and Fabrary as potential data sources.
=======
# Flesh and Blood Card Collection Management System
#### Video Demo: [YouTube Link](https://www.youtube.com/watch?v=yOGV3C9GR4s)
#### Description:
Flesh and blood is a card game similar to Magic, Pokemon, etc. Because it's a relatively small community for the game, there's only a handful of sites where people put decks together, manage collections, etc. The two main websites that are used are Fabdb.net and Fabrary.com

I won't use these sites to manage my collection because it's very tedious finding each card that I own, how many copies, what versions etc.

I decided that a way that I would like to manage my collection would be to load a particular decklist, see all the versions of all the cards in the list and then effectively check off all the ones I have. If later I open another decklist, I can see what cards I already own, or if I don't own any of cards. It could then be possible to export this collection and import it into one of these other websites, as they are a lot better for managing decks and "brewing."

## Technology Stack and Database Structure
My application is using HTML CSS and Flask Jinja HTML Templates along with HTMX to retrieve the rendered Jinja templates without having to write any javascript. I am using bootstrap to render the navbar and some tables etc. I wanted to keep it simple and have been into HTMX for a little while now, so this was a good opportunity to try it out more formally.

The backend is in Flask and has a sqlite database, which is constructed based on all of the available cards, where I found a JSON file on a repository, https://github.com/the-fab-cube/flesh-and-blood-cards. 

The database consists of only 4 tables

card: each unique card in flesh and blood, there's some properties of the cards there, but it's not an exhausted list of properties.
printing: each card can be printed in multiple versions (for collecting), but also in reprints
user_card_status: i needed to have a table to show the amount of cards that a user has of a given printing of a card
user: general user information like user pass email, but also connected back to the user_card_status.

I'm using checksum to check the value of the json file, this way if I update the file in a few months when there's more sets it should update the card database.

I've kept the routes pretty minimal.

There's some similar routes for login and register, like in the CS50 course from the stock app.

In the app there's a few buttons on the navbar, which can go to your collection, import decks, export collection and logout. 

## Routing and Functionality
The application maintains minimalistic routing, similar to the CS50 course’s stock app, covering essential actions like login and register. The navbar allows users to navigate to their collection, import decks, export their collection, and logout. The import and export functionalities are particularly challenging due to the need to align data formats from different sources like Fabdb and Fabrary. Because it's using HTMX, I'm not directly returning JSON to the front end. This could be an interesting approach for building out prototypes, especially for people with more of a backend focus in mind.

## Challenges and Learnings
The most difficult part of the project was definitely making sure that the two data formats of the cards from the two websites could be aligned so that I could do proper lookups with the card and printing tables.

Fabdb has an API, so it did help quite a bit, but it wasn't very consistent with the JSON file and had to find some common identifiers. Fabrary was even less typical as you could only export plain text, so this required a LOT of string manipulation based on the patterns.

The other issue was thinking about how to make sure that the deck that was submitted was actually rendered on the page. I decided to use session data to pass the deck between routes, but also to pass the filters of the dropdowns. The intent here was to provide filtering from the backend and not from javascript on the front end. For example if I have a foil type selected and a rarity selected, the backend would retrieve all the relevant printings from the database and then return those to the front end via a rendered template.

I think there's still some issues on some cards from some of the import where the string matching wasn't 100% perfect and won't hit every use-case, but I think for the scope of this project I'm really pleased.

I realized later that there were proper schemas for the JSON files, but this was after I had already created my database and decided to just have them as dictionaries in the flask route for the csv export (where I needed it the most).

I think it was really challenging and one thing I probably will remember is not to really use underscores or dashes as string separators. It's a little too easy to introduce bugs into the application and pretty challenging to troubleshoot.


## Installation
A `requirements.txt` file is included for easy setup. Install the requirements using:
```bash
pip install -r requirements.txt
```

> **Note**: The Flask-Login version is directly pulled from a specific Git commit due to some dependency issues with more recent versions of Flask. I think you'll run into some of those issues if you aren't using that specific version, or might have to downgrade flask otherwise.

## Future Improvements
I think I would focus on making some of the filters more usable, like adding icons and things that represent foiling better than just pure text, like maybe styling with CSS and adding javascript. Getting better aligned with the data to handle edge cases for some cards that aren't retrievable now is something worth investigating more, and working on exporting to other formats to be more of a Swiss army knife of deck collection maintenance would be really cool.
>>>>>>> e281f3c (initial commit)
