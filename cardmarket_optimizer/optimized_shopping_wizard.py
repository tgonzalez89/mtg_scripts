# TODO: Script that optimizes a 'wants' list.
# Input: cardmarket wants list id or maybe link?
# Algo should be something like this:
# Run the optimizer (input: filters, etc.)
# Add to the cart the cards from sellers that have many cards and that shipping not that expensive relative to the card cost
# Remove from the wants list the cards added to the card.
# Run the shopping wizard again and repeat the process.

# Ideas for criteria:
# First iteration:
# Only add to cart groups of cards that: a) have 3 or more cards and b) the price of the cards is at least half the price of the shipping
# Second iteration:
# Same as (1) but OR instead of AND (more flexible now)
# Third iteration:
# Add only groups that have 2 or more cards.
# Fourth iteration:
# No filters. By this point there's not much we can do.

# Record original,
# record total after optimizer and check which one is best
