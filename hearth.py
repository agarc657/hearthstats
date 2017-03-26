#!/usr/bin/env python

from cssselect import GenericTranslator, SelectorError
from lxml import html
import argparse
import json
import math
import requests
import re
import sqlite3
import sys

# Constants
DECKS_PER_PAGE = 25.0

class Deck:

	"""
	An object representing a single Hearthstone deck pulled from HearthPwn.
	"""

	def __init__(self, deckid, hero, decktype, rating, dust, updated, decklist):
	# returns (links, classes, types, ratings, dusts, epochs)
		"""
		Initialize a HearthPwn Deck object.

		Parameters:

		- 'deckid'   - the HearthPwn ID number of the deck (as seen in the URL)
		- 'hero'     - the Hearthstone class of the deck
		- 'type'     - the deck type (midrange, tempo, control, etc)
		- 'rating'   - the HearthPwn deck rating
		- 'dust'     - dust required to craft deck
		- 'updated'  - epoch timestamp of last update
		- 'decklist' - a list of Card objects
		"""
		
		self.deckid  = int(deckid)
		self.hero    = str(hero)
		self.type    = str(decktype)
		self.rating  = int(rating)
		self.dust    = int(dust)
		self.updated = int(updated)
		if decklist is not None:
			self.decklist = decklist
		else:
			self.decklist = []

	def __repr__(self):
		output = str(self.deckid) + '\n'
		for card in self.decklist:
			output += str(card.amount) + ' ' + card.cardname + '\n'
		return output

	def add_card(self, card):
		"""
		Add a Card to the end of a the Deck's decklist

		Parameters:

		'self' - the Deck object calling this function
		'card' - the Card being added to the Deck
		"""
		self.decklist.append(card)

	def get_length(self):
		"""
		Return the number of cards in the Deck.

		Parameters:

		'self' - the Deck object calling this function
		"""
		length = 0
		for card in self.decklist:
			length += card.amount
		return length


class Card:

	"""
	A simple object representing a card in a Hearthstone deck.
	"""

	def __init__(self, cardname, amount):
		"""
		Initialize a Hearthstone card object.

		Parameters:

		- 'cardname' - the text name of a Hearthstone card
		- 'amount' - the number of this card included in the parent deck
		"""
		self.cardname = str(cardname)
		self.amount = int(amount)

	def __repr__(self):
		return str(self.amount) + ' ' + self.cardname


def main():
	print("Loading Parser")
	parser = build_parser()
	args = parser.parse_args()
	print("Parser loaded")
	print("Connecting to SQLite3")
	conn = sqlite3.connect('hearth.db')
	cursor = conn.cursor()
	print("SQLite3 Connected")
	if args.builddecks:
		print("Rebuilding deck database...")
		if args.perclass:
			decks = get_decks_per_class(args.filtering, args.sorting,
										args.count, args.patch)
		else:
			decks = get_decks(args.filtering, args.sorting,
							  args.count, args.patch)
		populate_deck_db(decks, cursor)

	if args.buildcards:
		print("Rebuilding card database...")
		populate_card_db(get_cards(), cursor)
	
	print ("")
	conn.commit()
	
	# args.results NOT WORKING, removed while I work on it
	# if args.results:
		# TODO: More options when displaying results. For now, for anything
		# other than the default has to be queried from the DB directly.
		# results = get_db_card_percentages(cursor)
		# print("cardname, total decks using card, % decks using card, avg number in a deck")
		# for row in results:
			# if row[1] == 0 and row[2] == 0 and row[3] == 0:
				# continue
			# print( "{0}, {1}, {2:0.2f}%, {3:0.2f}".format(row[0], row[1], row[2], row[3]))

	conn.close()

	# if not args.builddecks and not args.buildcards and not args.results:
		# TODO: Swap to actual Python error handling.
		# print('ERROR: You must use either --builddecks, --buildcards, or '
			  # '--results')
		# parser.print_help()
	
	if not args.builddecks and not args.buildcards:
		# TODO: Swap to actual Python error handling.
		print('ERROR: You must use either --builddecks or --buildcards)
		parser.print_help()


def build_parser():
	"""
	Builds the parser object with all of the arguments and help text.
	"""
	desc = ("Scrape Hearthstone decks from HearthPwn, then build a SQLite "
			"database of the results. Also integrates with omgvamp's Mashape "
			"Hearthstone API (http://hearthstoneapi.com/) to build a table of "
			"card data that can be used to make more advanced queries.")
	parser = argparse.ArgumentParser(description=desc)
	parser.add_argument('--buildcards', action='store_true',
						help='(re)build card database from Mashape')
	parser.add_argument('--builddecks', action='store_true',
						help='(re)build deck database from HearthPwn')
	parser.add_argument('--perclass', action='store_true',
						help='get the same number of decks for each class')
	parser.add_argument('--count', type=int,
						help='number of decks to retrieve (per class, if'
							 ' --perclass is set)')
	parser.add_argument('--filtering',
						help='the HearthPwn filter used when finding decks, '
							 'as seen in the HearthPwn URL')
	parser.add_argument('--sorting',
						help='the HearthPwn sorting used when finding '
							 'decks, as seen in the HearthPwn URL after '
							 '"&sort="')
	parser.add_argument('--patch', type=int,
						help='the HearthPwn patch ID used when finding '
							 'decks, as seen in the HearthPwn URL after '
							 '"&filter-build="')
	# TODO: results not working, needs rework
	# parser.add_argument('--results', action='store_true',
						# help='for all cards, print the: cardname, total decks '
							 # 'using the card, percentage of decks '
							 # 'using the card, and average number of the card '
							 # 'in decks using the card')
	return parser


def get_decks_per_class(filtering=None, sorting=None, count=None, patch=None):
	"""
	Retrieve Decks from HearthPwn as a list of Deck objects, ensuring the same
	number of decks are retrieved for each class..

	Parameters:

	'filtering' - the HearthPwn filter used when finding decks, as seen in the
	HearthPwn URL
	'sorting' - the HearthPwn sorting used when finding decks, as seen in the
	HearthPwn URL after "&sort="
	'count' - number of decks to retrieve
	'patch' - the HearthPwn patch ID used when finding decks, as seen in the
	HearthPwn URL after "&filter-build="
	"""
	# For some  strange reason, HearthPwn assigns each class a "power of two"
	# value for filtering by class. For example, Warrior is filter-class=1024.
	# I'm not getting too granular at the moment, so just calculating powers
	# of two is fine.
	classes = [2**x for x in range(2, 11)]
	decks = []

	if not count:
		# Substitute a default count in here so that all classes return the
		# same number of decks.
		url = generate_url(filtering, sorting, patch)
		pagecount = get_pagecount(get_pagetree(url))
		count = int((pagecount * DECKS_PER_PAGE * 0.1) / len(classes))
	for classid in classes:
		decks += get_decks(filtering, sorting, count, patch, classid)
	return decks


def get_decks(filtering=None, sorting=None, count=None, patch=None, classid=None):
	"""
	Retrieve Decks from HearthPwn as a list of Deck objects.

	Parameters:

	'filtering' - the HearthPwn filter used when finding decks, as seen in the
	HearthPwn URL
	'sorting' - the HearthPwn sorting used when finding decks, as seen in the
	HearthPwn URL after "&sort="
	'count' - number of decks to retrieve
	'patch' - the HearthPwn patch ID used when finding decks, as seen in the
	HearthPwn URL after "&filter-build="
	'classid' - the HearthPwn class ID used when finding decks, as seen in the
	HearthPwn URL after "&filter-class="
	"""
	decks_metainfo = get_deck_metainfo(filtering, sorting, count, patch, classid)
	
	decks = [Deck(deck[0], deck[1], deck[2], deck[3], deck[4], deck[5], get_deck_list(deck[0]))
			 for deck in decks_metainfo]
	
	return decks


def get_deck_list(deckid):
	"""
	For a given HearthPwn deck ID, return a list of Cards that belong to that
	deck.

	Parameters:

	'deckid' - a HearthPwn deck ID
	"""
	sys.stdout.write(".")
	
	# http://www.hearthpwn.com/decks/listing/ + /neutral or /class
	url = 'http://www.hearthpwn.com/decks/listing/'
	css = '#cards > tbody > tr > td.col-name'

	cards = []

	# Class Cards
	pagetree = get_pagetree(url + str(deckid) + '/class')
	elements = get_elements_from_page(pagetree, css)
	for element in elements:
		card = html.tostring(element, method='text', encoding='UTF-8')
		cards.append(card)

	# Neutral Cards
	pagetree = get_pagetree(url + str(deckid) + '/neutral')
	elements = get_elements_from_page(pagetree, css)
	for element in elements:
		card = html.tostring(element, method='text', encoding='UTF-8')
		cards.append(card)

	regex = re.compile(b'(.+)\r\n.+\r\n\r\n \xc3\x97 (\d+)')
	deck = []
	for card in cards:
		match = re.search(regex, card)
		if match:
			cardname = match.group(1).strip()
			amount = int(match.group(2))
			deck.append(Card(cardname, amount))

	return deck


def get_pagetree(url):
	"""
	Using requests and LXML's HTML module, retrieve a URL and return the page
	as a tree of LXML HTML elements.

	Parameters:

	'url' - the URL of the webpage to get
	"""
	response = requests.get(url)
	pagetree = html.fromstring(response.text)
	return pagetree


def get_elements_from_page(pagetree, css):
	"""
	Using cssselect's GenericTranslater (to translate the selector into XPATH),
	return only elements that match a CSS selector.

	Parameters:

	'pagetree' - the tree of elements to select from
	'css' - the CSS selector
	"""

	# Have to convert the CSS selectors to XPATH selectors (gross).
	try:
		expression = GenericTranslator().css_to_xpath(css)
	except SelectorError:
		print('Invalid selector.')
		return
	elements = pagetree.xpath(expression)
	return elements


def get_attributes_from_page(pagetree, css, attribute):
	"""
	Using LXML, get all of the attributes from a pagetree that match a css
	selector, and then return a list containing the contents of a given
	attribute for each element.

	Parameters:

	'pagetree' - the tree of elements to select from
	'css' - the CSS selector
	"""
	elements = get_elements_from_page(pagetree, css)
	attributes = [element.attrib[attribute] for element in elements]
	return attributes


def get_latest_patch():
	"""
	Get the latest patch ID from HearthPwn
	"""
	pagetree = get_pagetree('http://www.hearthpwn.com/decks')
	css = '#filter-build > option'
	patches = get_attributes_from_page(pagetree, css, 'value')
	# Filtering out the empty/none result using list comprehension magic.
	patches = [patch for patch in patches if patch]
	patches.sort(key=int, reverse=True)
	return patches[0]


def get_pagecount(pagetree):
	"""
	Gets the number of pages on a HearthPwn search from a pagetree.
	"""
	css = ('#content > section > div > div > div.listing-header >'
		   'div.b-pagination.b-pagination-a > ul > li:nth-child(7) > a')
	pagecount = get_elements_from_page(pagetree, css)[0].text
	return int(pagecount)


def generate_url(filtering=None, sorting=None, patch=None, classid=None):
	"""
	Combines all factors used for sorting into a url.

	Default values are also substitued in here.

	Parameters:

	'filtering' - the HearthPwn filter used when finding decks, as seen in the
	HearthPwn URL
	'sorting' - the HearthPwn sorting used when finding decks, as seen in the
	HearthPwn URL after "&sort="
	'patch' - the HearthPwn patch ID used when finding decks, as seen in the
	HearthPwn URL after "&filter-build="
	'classid' - the HearthPwn class ID used when finding decks, as seen in the
	HearthPwn URL after "&filter-class="
	"""

	if not filtering:
		filtering = ('filter-is-forge=2&filter-unreleased-cards=f'
					 '&filter-deck-tag=1&filter-deck-type-val=8'
					 '&filter-deck-type-op=4'
					 '&filter-quality-free-max=29')

	if not sorting:
		sorting = '-viewcount'

	if not patch:
		patch = get_latest_patch()

	# To make things a bit easier on us, sorting, patch, and classid are all
	# compiled into the filtering.

	# Combine patch and filtering
	if patch and filtering:
		# This is separate from the filter attribute to make it easier to only
		# pull decks from the most recent patch.
		if filtering[-1] != '?' and filtering[-1] != '&':
			filtering += '&'
		filtering += 'filter-build=' + str(patch)
	elif patch:
		# Not currently used as filtering has a default above, but leaving just
		# in case I change how this works in the future.
		filtering = 'filter-build=' + str(patch)

	# Combine classid and filtering
	if classid and filtering:
		# This is separate from the filter attribute to make it easier to only
		# pull decks from a single class. This means we can, for example, get
		# the top 1000 decks from each class.
		if filtering[-1] != '?' and filtering[-1] != '&':
			filtering += '&'
		filtering += 'filter-class=' + str(classid)
	elif classid:
		filtering = 'filter-class=' + str(classid)

	# Combine sorting and filtering
	if sorting and filtering:
		if filtering[-1] != '?' and filtering[-1] != '&':
				filtering += '&'
		filtering += 'sort=' + sorting
	elif sorting:
		filtering = 'sort=' + sorting

	if filtering:
		url = 'http://www.hearthpwn.com/decks?' + filtering
	else:
		url = 'http://www.hearthpwn.com/decks'
	return url


# Returns (deckid, class)
def get_deck_metainfo(filtering=None, sorting=None, count=None, patch=None, classid=None):
	"""
	Gets a list of (deckid, class) tuples from HearthPwn using the provided
	paramters.

	Parameters:

	'filtering' - the HearthPwn filter used when finding decks, as seen in the
	HearthPwn URL
	'sorting' - the HearthPwn sorting used when finding decks, as seen in the
	HearthPwn URL after "&sort="
	'count' - number of decks to retrieve
	'patch' - the HearthPwn patch ID used when finding decks, as seen in the
	HearthPwn URL after "&filter-build="
	'classid' - the HearthPwn class ID used when finding decks, as seen in the
	HearthPwn URL after "&filter-class="
	"""
	sys.stdout.write(".")
	url = generate_url(filtering, sorting, patch, classid)
	
	if not count:
		pagecount = get_pagecount(get_pagetree(url))
		count = int(pagecount * .1)

	pagecount = math.ceil(count / DECKS_PER_PAGE)

	regex = re.compile('^\s*\/decks\/(\d+)')
	output = []
	for pagenum in range(1, int(pagecount)+1):  # Adding one as range is exclusive

		# For each page, get a list of decks from all of the href attributes.
		# Then for each list of decks, pull out the deck ID using regex.
		# Finally, if there is a match, append the deck ID to the deckids list.

		if pagenum == 1:
			pagetree = get_pagetree(url)
		else:
			page = '&page=' + str(pagenum)
			pagetree = get_pagetree(url + page)

		# This CSS selector grabs all of the a (HTML hyperlink) elements in the
		# HearthPwn decks table (being specific to make sure we get the right
		# elements.) We can pull the deck IDs from the HREF attribute.
		css = '#decks > tbody > tr > td.col-name > div > span > a'
		links = get_elements_from_page(pagetree, css)
		css = '#decks > tbody > tr > td.col-deck-type > span'
		decktypes = get_elements_from_page(pagetree, css)
		css = '#decks > tbody > tr > td.col-class'
		heros = get_elements_from_page(pagetree, css)
		css = '#decks > tbody > tr > td.col-ratings > div'
		ratings = get_elements_from_page(pagetree, css)
		css = '#decks > tbody > tr > td.col-dust-cost'
		dusts = get_elements_from_page(pagetree, css)
		css = '#decks > tbody > tr > td.col-updated > abbr'
		epochs = get_elements_from_page(pagetree, css)

		links = [link.attrib['href'] for link in links]
		types = [decktype.text for decktype in decktypes]
		classes = [hero.text for hero in heros]
		ratings = [rating.text for rating in ratings]
		dusts = [dust.text.replace(",", "").replace("k","00").replace(".","") for dust in dusts]
		epochs = [epoch.attrib['data-epoch'] for epoch in epochs]
		
		for x in range(len(links)):
			match = re.search(regex, links[x])
			links[x] = int(match.group(1))
		
		output += list(zip(links, classes, types, ratings, dusts, epochs))

	return output[:count]


def populate_deck_db(decks, cursor):
	"""
	(Re)populates deck information in the SQLite database.

	Parameters:

	'decks' - a list of Deck objects
	'cursor' - a SQLite3 cursor object
	"""
	cursor.execute('DROP TABLE IF EXISTS decks')
	cursor.execute('DROP TABLE IF EXISTS deck_lists')
	cursor.execute('''CREATE TABLE IF NOT EXISTS decks
			 (deckid integer primary key, class text, type text, rating integer, dust integer, updated integer)
			 ''')
			 # (deckid AUTOINCREMENT integer primary key, class text, type text, rating integer, dust integer, updated integer)

	cursor.execute('''CREATE TABLE IF NOT EXISTS deck_lists
			 (deckid integer, cardname text, amount integer,
			  PRIMARY KEY (deckid, cardname))''')
	for deck in decks:
		cursor.execute('INSERT INTO decks (class, type, rating, dust, updated) VALUES ( ?, ?, ?, ?, ?)',
			#(deck.deckid, deck.hero, deck.type, deck.rating, deck.dust, deck.updated))
			(deck.hero, deck.type, deck.rating, deck.dust, deck.updated))
		last_id = cursor.lastrowid
		for card in deck.decklist:
			cursor.execute('INSERT INTO deck_lists VALUES (?, ?, ?)',
						   (last_id, card.cardname, card.amount))
	return


def get_cards():
	"""
	Gets a list of all current Hearthstone cards from omgvamp's mashape
	Hearthstone API, and returns them as a json object.
	"""
	with open("mashape_key.txt", "r") as mashape_key:
		api_key = mashape_key.read()
	url = "https://omgvamp-hearthstone-v1.p.mashape.com/cards?collectible=1"
	headers = {"X-Mashape-Key": api_key}
	response = requests.get(url, headers=headers)
	cards = json.loads(response.text)
	return cards


def populate_card_db(cards, cursor):
	"""
	(Re)populates card information in the SQLite database.

	Parameters:

	'cards' - a list of Card objects
	'cursor' - a SQLite3 cursor object
	"""
	cursor.execute('DROP TABLE IF EXISTS cards')
	cursor.execute('''CREATE TABLE IF NOT EXISTS cards
					  (cardname text, cardset text,
					   hero text, rarity text,
					   PRIMARY KEY (cardname))''')
	# Removing invalid sets from our results. For the most part, these sets are
	# empty lists as we filter out non-collectible cards. The Mashape API
	# includles cardsets without collectible cards, such as 'System',
	# 'Credits', and 'Debug'. We also explicitly remove the 'Hero Skins' set as
	# they are considered "collectible cards" by HearthStone, but not for our
	# purposes. We will filter out cards where "type": "Hero" later for
	# similar reasons.
	valid_cardsets = {cardset: cards for cardset, cards in cards.items()
						if cards and cardset != 'Hero Skins'}
	for cardset in valid_cardsets:
		for card in cards[cardset]:
			if card['type'] != 'Hero':
				cursor.execute('INSERT INTO cards VALUES (?, ?, ?, ?)',
							   (card['name'], card['cardSet'],
								card.get('playerClass', 'Neutral'),
								card['rarity']))
	return


def get_db_deck_count(cursor):
	"""
	Returns the number of decks currently in the database.

	Parameters:

	'cursor' - a SQLite3 cursor object
	"""
	cursor.execute('SELECT count(*) FROM decks')
	return cursor.fetchone()[0]

def get_db_deck_updated(cursor, deckid):
	"""
	Returns the timestamp of the specified deck

	Parameters:

	'cursor' - a SQLite3 cursor object
	'deckid' - a HearthPwn deck ID
	"""
	cursor.execute('SELECT updated FROM decks WHERE deckid IS ?', (deckid,))
	return cursor.fetchone()[0]

def get_db_card_percentages(cursor, cardsets=None):
	"""
	For all cards, return: (cardname, total decks using the card, percentage
	of decks using the card, and average number of the card in a deck) from
	the database.

	Parameters:

	'cursor' - a SQLite3 cursor object
	'cardsets' - Hearthstone card sets to include in the results (all
	others are implicitly excluded)
	"""
	count = get_db_deck_count(cursor)
	if cardsets:
		sql = '''
			  select cards.cardname,
			  case
				when deck_lists.cardname is null
				  then 0
				else count(*)
			  end as [Total],
			  case
				when deck_lists.cardname is null
				  then 0.0
				else count(*)/? * 100.0
			  end as [Percent],
			  avg(coalesce(deck_lists.amount, 0)) as [Average Per Deck]
			  from cards
			  left join deck_lists
			  on cards.cardname = deck_lists.cardname
			  where cards.cardset in (%s)
			  group by cards.cardname
			  order by Percent desc
		  ''' % ','.join('?' * len(cardsets))
		params = [float(count)]
		print(params)
		for cardset in cardsets:
			params.append(cardset)
		results = cursor.execute(sql, params)
	else:
		sql = '''
			  select cards.cardname,
			  case
				  when deck_lists.cardname is null
					  then 0
					  else count(*)
			  end as [Total],
			  case
				  when deck_lists.cardname is null
					  then 0.0
					  else count(*)/? * 100.0
			  end as [Percent],
			  avg(coalesce(deck_lists.amount, 0)) as [Average Per Deck]
			  from cards
			  left join deck_lists
			  on cards.cardname = deck_lists.cardname
			  group by cards.cardname
			  order by Percent desc
			  '''
		results = cursor.execute(sql, (float(count), ))
	return results

if __name__ == "__main__":
	# Execute only if run as a script
	main()
