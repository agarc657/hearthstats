# hearthstats

Scrape Hearthstone decks from HearthPwn, then populate a table in a SQLite database 
using the results. Also integrates with omgvamp's Mashape Hearthstone API
(http://hearthstoneapi.com/) to build a table of card data that can be used to
make more advanced queries.

Requires lxml, cssselect, and requests packages.

```
usage: hearth.py [-h] [--buildcards] [--builddecks] [--perclass]
                 [--count COUNT] [--filtering FILTERING] [--sorting SORTING]
                 [--patch PATCH]

optional arguments:
  -h, --help            show this help message and exit
  --buildcards          (re)build card database from Mashape
  --builddecks          (re)build deck database from HearthPwn
  --perclass            get the same number of decks for each class
  --count COUNT         number of decks to retrieve (per class, if --perclass
                        is set)
  --filtering FILTERING
                        the HearthPwn filter used when finding decks, as seen
                        in the HearthPwn URL
  --sorting SORTING     the HearthPwn sorting used when finding decks, as seen
                        in the HearthPwn URL after "&sort="
  --patch PATCH         the HearthPwn patch ID used when finding decks, as
                        seen in the HearthPwn URL after "&filter-build="
```

Note: Before populating the card database, you must first register for an API key at 
Mashape.com. Once you have your API key, create a mashape_key.txt file in the same 
folder as the script and paste your API key into it.
