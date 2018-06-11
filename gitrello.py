import asyncio
import os

from trello import TrelloClient
from github3 import GitHub


DEFAULT_SYNC_TIMEOUT = 60

# TODO: read this from yaml
trelloLists = {
    'To review': 'is:open is:pr archived:false updated:>=2018-01-01 review-requested:vrutkovs',
    'Assigned': 'is:open is:pr archived:false updated:>=2018-01-01 assignee:vrutkovs',
    'Waiting for review': 'is:open is:pr archived:false updated:>=2018-01-01 review:none author:vrutkovs',
    'Changes requested': 'is:open is:pr archived:false updated:>=2018-01-01 review:changes_requested author:vrutkovs',
    'Approved': 'is:open is:pr archived:false updated:>=2018-01-01 author:vrutkovs label:lgtm',
    'Fix tests': 'is:open is:pr archived:false updated:>=2018-01-01 author:vrutkovs status:failure',
    'Needs rebase': 'is:open is:pr archived:false updated:>=2018-01-01 author:vrutkovs label:needs-rebase',
}

async def read_config():
    app_key = os.environ["GITRELLO_APPKEY"]
    trello_token = os.environ["GITRELLO_TRELLO_TOKEN"]
    sync_timeout = os.environ.get("GITRELLO_SYNC_TIMEOUT") or DEFAULT_SYNC_TIMEOUT

    trello_client = TrelloClient(api_key=app_key, token=trello_token)
    board = trello_client.get_board(os.environ["GITRELLO_BOARDID"])

    # TODO: add optional login/token to increase rate limits
    github_config = {}
    github_token = os.environ.get("GITRELLO_GITHUB_TOKEN")
    if github_token:
        github_config = {'token': github_token}
    github_client = GitHub(**github_config)

    return {
        'board': board,
        'github': github_client,
        'syncTimeout': sync_timeout,
    }

async def create_missing_lists(config):
    board = config['board']

    trello_lists = dict([(x.name, x.id) for x in board.list_lists()])

    existing_list_names = trello_lists.keys()
    required_list_names = trelloLists.keys()

    lists_to_add = required_list_names - existing_list_names
    lists_to_remove = existing_list_names - required_list_names

    for lst in lists_to_add:
        print("Adding list {}".format(lst))
        board.add_list(lst)

    for lst in lists_to_remove:
        print("Closing list {}".format(lst))
        lst_id = trello_lists[lst]
        board.get_list(lst_id).close()

async def sync(config):
    print("Syncing PRs")
    gh = config['github']
    board = config['board']
    for list_name in trelloLists:
        search_query = trelloLists[list_name]
        trello_list = [x for x in board.list_lists() if x.name == list_name][0]
        search_results = gh.search_issues(search_query)

        # Find out which cards should be removed
        prs = dict([x.as_dict()['title'], x.as_dict()] for x in search_results)
        existing_card_names = [x.name for x in trello_list.list_cards()]

        cards_to_remove = existing_card_names - prs.keys()
        cards_to_create = prs.keys() - existing_card_names

        print("Found {0} cards to remove and {1} cards to add in '{2}'".format(
              len(cards_to_remove), len(cards_to_create), list_name))

        for card_name in cards_to_remove:
            print("Removing '{0}' card from '{1}' list".format(card_name, list_name))
            await remove_task(card_name, trello_list)

        for card_name in cards_to_create:
            print("Adding '{0}' card to '{1}' list".format(card_name, list_name))
            pr = prs[card_name]
            await add_task(pr, trello_list)


async def add_task(pr, trello_list):
    url = pr['html_url']
    title = pr['title']
    card = trello_list.add_card(title)
    card.attach(url=url)

async def remove_task(title, trello_list):
    for card in trello_list.list_cards():
        if card.name == title:
            card.delete()
            return

async def main(loop):
    config = await read_config()
    await create_missing_lists(config)

    # Periodically sync PRs
    while True:
        try:
            await sync(config)
        except Exception as e:
            print(str(e))
        await asyncio.sleep(config['syncTimeout'], loop=loop)

loop = asyncio.get_event_loop()
loop.run_until_complete(main(loop))
loop.close()
