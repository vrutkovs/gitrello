import asyncio
import os
import yaml
import concurrent.futures

from trello import TrelloClient
from github3 import GitHub


DEFAULT_SYNC_TIMEOUT = 60
DEFAULT_WORKERS = 4

config_path = os.path.abspath('config/gitrello.yml')

def get_config(path):
    with open(path) as f:
        config = yaml.load(f)
    return config

async def read_config():
    with open(config_path) as f:
        config = yaml.load(f)

    assert 'trello_appkey' in config
    assert 'trello_token' in config
    assert 'trello_boardid' in config
    assert 'lists' in config

    config['sync_timeout'] = config.get("sync_timeout") or DEFAULT_SYNC_TIMEOUT
    config['workers'] = config.get("workers") or DEFAULT_WORKERS

    trello_client = TrelloClient(api_key=config['trello_appkey'], token=config['trello_token'])
    board = trello_client.get_board(config['trello_boardid'])

    github_config = {}
    github_token = config.get("github_token")
    if github_token:
        github_config = {'token': github_token}
    github_client = GitHub(**github_config)

    config.update({
        'board': board,
        'github': github_client,
    })
    return config

async def create_missing_lists(config):
    board = config['board']

    trello_lists = dict([(x.name, x.id) for x in board.list_lists()])

    existing_list_names = trello_lists.keys()
    required_list_names = config['lists'].keys()

    lists_to_add = required_list_names - existing_list_names
    lists_to_remove = existing_list_names - required_list_names

    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=config['workers']) as executor:
        for lst in lists_to_add:
            futures.append(loop.run_in_executor(executor, add_list, board, lst))
        for lst in lists_to_remove:
            futures.append(loop.run_in_executor(executor, close_list, board, trello_lists, lst))

    await asyncio.gather(*futures)

def add_list(board, lst):
    print(f"Adding list {lst}")
    board.add_list(lst)

def close_list(board, trello_lists, lst):
    print(f"Closing list {lst}")
    lst_id = trello_lists[lst]
    trello_list = board.get_list(lst_id)
    trello_list.close()

def prs_to_sync(config, list_name, trello_list):
    gh = config['github']
    search_query = config['lists'][list_name]

    search_results = gh.search_issues(search_query)
    prs = dict([x.as_dict()['title'], x.as_dict()] for x in search_results)
    existing_card_names = [x.name for x in trello_list.list_cards()]
    return prs, existing_card_names

async def get_lists(config, trello_lists):
    for list_name in config['lists']:
        trello_list = [x for x in trello_lists if x.name == list_name][0]
        yield list_name, trello_list

async def sync(config):
    print("Syncing PRs")
    gh = config['github']
    board = config['board']

    trello_lists = board.list_lists()

    # Run searches in parallel
    search_inputs = []
    search_futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=config['workers']) as executor:
        async for list_name, trello_list in get_lists(config, trello_lists):
            search_input = (list_name, trello_list)
            search_inputs.append(search_input)
            search_futures.append(loop.run_in_executor(executor, prs_to_sync, config, *search_input))

    search_results = await asyncio.gather(*search_futures)

    # Collect search results and run actions in parallel
    action_args = []
    for (search_input, result) in zip(search_inputs, search_results):
        list_name, trello_list = search_input
        prs, existing_card_names = result
        cards_to_remove = existing_card_names - prs.keys()
        cards_to_create = prs.keys() - existing_card_names

        print("Found {0} cards to remove and {1} cards to add in '{2}'".format(
              len(cards_to_remove), len(cards_to_create), list_name))

        for card_name in cards_to_remove:
            print(f"Removing '{card_name}' card from '{list_name}' list")
            action_args.append((remove_task, card_name, trello_list))

        for card_name in cards_to_create:
            print(f"Adding '{card_name}' card to '{list_name}' list")
            pr = prs[card_name]
            action_args.append((add_task, pr, trello_list))

    # No actions to be performed - exit
    if not action_args:
        print("No actions to perform")
        return

    action_futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=config['workers']) as executor:
        for action_arg in action_args:
            action_futures.append(loop.run_in_executor(executor, *action_arg))

    await asyncio.gather(*action_futures)

def add_task(pr, trello_list):
    url = pr['html_url']
    title = pr['title']
    card = trello_list.add_card(title)
    card.attach(url=url)

def remove_task(title, trello_list):
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
        await asyncio.sleep(config['sync_timeout'], loop=loop)

loop = asyncio.get_event_loop()
loop.run_until_complete(main(loop))
loop.close()
