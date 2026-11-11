"""Original, game-specific editorial summaries for titles in the original Elmos World library.

These are descriptive facts rather than text copied from store listings.  Entries are
matched by *whole normalized title*, never partial title similarity; this prevents
mislabeling sequels/remakes. Public store lookup remains available for other games.
"""
import re

def key(title):
    return ' '.join(re.findall(r'[a-z0-9]+', str(title).casefold()))

# Title, an overview, shorter hero/deck line, genres, developer (when confidently known).
CATALOG = {
    '7 days to die': (
        'In a hostile open world overrun by the undead, gather resources, craft weapons, build a defensible base, and survive increasingly dangerous zombie hordes. Explore, loot, and shape your own survival strategy in this sandbox adventure.',
        'Build, scavenge, and survive a zombie-filled open world.',
        ['Survival', 'Open World', 'Crafting'], 'The Fun Pimps'),
    'buckshot roulette': (
        'Face a mysterious dealer in a dangerous game of chance played with a shotgun. Read the chamber, weigh each risk, and use special items to turn the odds in your favor as the rounds become more intense.',
        'Outthink the dealer in a tense tabletop game of chance.',
        ['Strategy', 'Horror', 'Indie'], 'Mike Klubnika'),
    'control ue': (
        'Step into the shifting headquarters of the Federal Bureau of Control as Jesse Faden searches for answers about her past. Wield supernatural abilities and a transforming weapon while investigating an otherworldly threat in this action-adventure mystery.',
        'Enter the Oldest House and uncover a supernatural mystery.',
        ['Action', 'Adventure', 'Supernatural'], 'Remedy Entertainment'),
    'control ultimate edition': (
        'Step into the shifting headquarters of the Federal Bureau of Control as Jesse Faden searches for answers about her past. Wield supernatural abilities and a transforming weapon while investigating an otherworldly threat in this action-adventure mystery.',
        'Enter the Oldest House and uncover a supernatural mystery.',
        ['Action', 'Adventure', 'Supernatural'], 'Remedy Entertainment'),
    'keep talking and nobody explodes': (
        'Work together to defuse a ticking bomb: one player sees the device while the others consult a separate bomb-defusal manual. Clear communication, calm reasoning, and quick decisions are the only way to solve each puzzle before time runs out.',
        'Defuse bombs together—communication is everything.',
        ['Co-op', 'Puzzle', 'Party'], 'Steel Crate Games'),
    'outer wilds': (
        'Explore a hand-crafted solar system caught in a mysterious time loop. Travel between unusual planets, follow clues left by an ancient civilization, and piece together a cosmic mystery through curiosity and discovery.',
        'Unravel a cosmic mystery across a looping solar system.',
        ['Exploration', 'Adventure', 'Mystery'], 'Mobius Digital'),
    'sekiro shadows die twice': (
        'Play as a shinobi bound by duty in a reimagined late-1500s Japan. Master precise sword combat, stealth, and prosthetic tools as you confront formidable opponents and fight to reclaim your lost honor.',
        'Master the blade in a demanding shinobi adventure.',
        ['Action', 'Adventure', 'Soulslike'], 'FromSoftware'),
    'silent hill 2': (
        'James Sunderland travels to the fog-covered town of Silent Hill after receiving a letter from his deceased wife. Explore haunting environments, solve puzzles, and face disturbing creatures in a psychological horror story built around guilt and grief.',
        'A haunting psychological horror journey into Silent Hill.',
        ['Psychological Horror', 'Survival Horror', 'Adventure'], ''),
    'the jackbox party pack 7': (
        'Gather friends for five distinct party games: Quiplash 3, The Devils and the Details, Champ’d Up, Talking Points, and Blather ’Round. Join from a phone or other web-enabled device and compete through creative answers, drawings, teamwork, and guessing.',
        'Five party games made for friends and big laughs.',
        ['Party', 'Multiplayer', 'Trivia'], 'Jackbox Games'),
    'ssx 2012': (
        'Race, trick, and survive across dramatic mountain ranges in this snowboarding game. Chase high scores, tackle perilous terrain, and conquer the nine Deadly Descents while pushing your speed and style to the limit.',
        'Race, trick, and survive extreme mountain descents.',
        ['Racing', 'Sports', 'Snowboarding'], 'EA Canada'),
    'ssx tricky': (
        'Compete in wild, arcade-style snowboarding races packed with over-the-top tricks, shortcuts, and rival riders. Chain stunts to build your boost and race toward the finish in a fast, colorful snowboarding challenge.',
        'Big tricks, fierce rivals, and arcade snowboarding.',
        ['Racing', 'Sports', 'Snowboarding'], 'EA Canada'),
}

def curated_metadata(title):
    record = CATALOG.get(key(title))
    if not record:
        return None
    description, tagline, genres, developer = record
    return {'available': True, 'title': title, 'description': description,
            'tagline': tagline, 'genres': genres, 'developer': developer,
            'release': '', 'screenshots': [], 'source': 'Elmos library'}
