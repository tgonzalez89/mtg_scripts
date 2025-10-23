# MTG helper scripts

Scripts to help automate various tasks related to Magic: The Gathering.

## Prerequisites

Python 3 (a recent version).

### Install required Python packages
```
pip install requirements.txt
```

If you open the requirements.txt you'll see which scripts need which packages.
If you don't want to install all of them just pick and choose which ones you want.

## How to run

Run them using Python:
```
python <script_path> [args...]
```

To know about the specific arguments and options each script needs, just run:
```
python <script_path> --help
```

## Build Base Deck

Useful to generate an initial card list to create a new Commander deck. Pulls data from EDHREC and finds the most popular cards and generates a `main_deck.txt` file with the most included/most synergistic cards and a `considering.txt` file with other cards that match the provided filters but that are not as popular. You can import these files into your favorite deck building tool.

**Note:** This script checks both the 'average' and the 'budget' lists of cards.
I did it this way because I focus on building budget decks.
You can remove the budget parts if needed or change them to use the 'expensive' lists of cards instead.
In the future I might update the script to be able to enable/disable the budget/expensive lists or to choose which ones
you want to consider (budget/average/expensive).

Inputs:
* Commander
  * Name of the commander. Must match exactly.
  * If partners, the names must be separated by a space. Partners order matter. EDHREC is peculiar about this.
  * You can give multiple of them and the script will merge their data. Useful for similar commanders (like Ruby, Daring Tracker and Radha, Heir to Keld).
* Themes
  * Pulls the lists of cards for these themes. If not given, doesn't filter by theme.
* Synergy threshold
  * Only cards that have EDHREC's synergy value above this threshold are taken into account.
  * Must be between 0 and 1 (15% would be 0.15, for example).
* Inclusion threshold
  * Only cards that have a deck inclusion above this threshold are taken into account.
  * Must be between 0 and 1 (15% would be 0.15, for example).
* Price threshold
  * Only cards below this threshold are taken into account.
  * Must be more than 0.
* Vendor
  * Vendor to use to get the cards prices. Uses Card Kingdom by default.

Outputs:
* main_deck.txt
  * File with the most included and most synergistic cards. Cards that you should most probably include in your deck.
* considering.txt
  * File with other cards that match the provided filters but that are not as popular. Consider them for your deck.

## Calculate To Purchase

Calculate which cards you need to purchase to make one or more new decks.
Uses your collection and your decks to check which cards from you collection are available (not being actively used in any deck you own) and then calculates which cards you don't have and makes a list of the cards you actually need.

Inputs:

## CardMarket Optimizer

## CardTrader Optimizer

## Forge Auto Battler

## Other Scripts
