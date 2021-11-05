from typing import Dict

import json
from pathlib import Path

import requests


# Endpoints
BASE_URL = 'https://kara.moe/'
GET_KARA_URL = BASE_URL + 'api/karas/'
DOWNLOADS_URL = BASE_URL + 'downloads/'
LYRICS_URL = DOWNLOADS_URL + 'lyrics/'
MEDIA_URL = DOWNLOADS_URL + 'medias/'


def get_kara_data(kara_id: str) -> Dict[str, str]:
    """Function to get relevant data about a karaoke map from kara.

    Args:
        kara_id (str): The ID of the kara.

    Raises:
        ValueError: Raised if an error with the response occurs.

    Returns:
        Dict[str, str]: Data about the kara.
    """

    response = requests.get(GET_KARA_URL + kara_id)
    if response.status_code != 200:
        print('\033[0;31mError:\033[0m Request to kara returned {0}!'.format(response.status_code))
        raise ValueError('Unexpected response from kara.')

    data = json.loads(response.content)

    kara_data = {
        'title': data['titles']['eng'],
        'sub_file': data['subfile'],
        'media_file': data['mediafile'],
        'language': data['langs'][0]['i18n']['eng']
    }


    # Get singers
    artists = ''
    for singer in data['singers']:
        artists += singer['name'] + ' & '
    kara_data['artists'] = artists[:-3]

    # Get mapper
    authors = ''
    for singer in data['authors']:
        authors += singer['name'] + ' & '
    kara_data['authors'] = authors[:-3]

    return kara_data


def get_sub_file(filename: str, download_directory: Path) -> None:
    """Function to download the subtitle file for a kara.

    Args:
        filename (str): The name of the subtitle file.
        download_directory (Path): The path to download the file to.

    Raises:
        ValueError: Raised if an error with the response occurs.
    """

    response = requests.get(LYRICS_URL + filename)
    if response.status_code != 200:
        print('\033[0;31mError:\033[0m Request to kara returned {0}!'.format(response.status_code))
        raise ValueError('Unexpected response from kara.')

    with open(download_directory.joinpath(filename), 'wb') as f:
        f.write(response.content)


def get_media_file(filename: str, download_directory: Path) -> None:
    """Function to download the media file for a kara.

    Args:
        filename (str): The name of the media file.
        download_directory (Path): The path to download the file to.

    Raises:
        ValueError: Raised if an error with the response occurs.
    """

    response = requests.get(MEDIA_URL + filename)
    if response.status_code != 200:
        print('\033[0;31mError:\033[0m Request to kara returned {0}!'.format(response.status_code))
        raise ValueError('Unexpected response from kara.')

    with open(download_directory.joinpath(filename), 'wb') as f:
        f.write(response.content)
