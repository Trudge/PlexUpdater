import json
import requests
import xml.etree.cElementTree as ET
import configparser
import os
import hashlib
import getpass
import subprocess
import shutil
import tqdm  # this is a non standard library, used for the download progress bar.  sudo pip3 install tqdm

config_file = "/Volumes/Scripts/config/config.ini"


class plexServer():
    def __init__(self, name):
        self.name = name
        plexServer._read_config(self)
        plexServer._set_download_url(self)
        plexServer._get_web_data(self)
        plexServer._get_server_data(self)
        plexServer._get_server_version(self)
        plexServer._get_download_details(self)
        plexServer._upgrade_available(self)


    def _set_download_url(self):
        if self.plexPlexpass == ("yes" or "1" or "True"):
            self.plexDownloadUrl = self.plexDownloadUrl + "?channel=plexpass"


    def _read_config(self):
        config = configparser.ConfigParser()
        config.read(config_file)
        self._config = config._sections
        self.DEFAULT_TIMEOUT = int(config['default']['default_timeout'])
        self.plexToken = config['plex']['plex_token']
        self.plexHostUrl = config['plex']['host_url']
        self.plexDownloadUrl = config['plex']['download_url']
        self.plexDistro = config['plex']['distro']
        self.plexBuild = config['plex']['build']
        self.plexDownloadDir = config['plex']['download_directory']
        self.plexArchiveDir = config['plex']['archive_directory']
        self.plexPlexpass = config['plex']['plexpass']
        self.prowlApiKey = config['prowl']['api_key']
        self.prowlPriority = config['prowl']['priority']


    def _get_web_data(self):
        s = requests.Session()
        s.headers = {'X-Plex-Token': self.plexToken}
        r = s.get(self.plexDownloadUrl, timeout=self.DEFAULT_TIMEOUT)
        r.raise_for_status()
        self._webData = json.loads(r.text)
        return self


    def _get_server_data(self):
        s = requests.Session()
        s.headers = {'X-Plex-Token': self.plexToken}
        r = s.get(self.plexHostUrl, timeout=self.DEFAULT_TIMEOUT)
        r.raise_for_status()
        self._serverData = ET.XML(r.text)
        return self


    def _get_server_version(self):
        self.currentVersion = self._serverData.attrib['version']
        self.friendlyName = self._serverData.attrib['friendlyName']
        return self


    def _get_download_details(self):
        for i in range(len(self._webData['computer']['Linux']['releases'])):
            if self._webData['computer']['Linux']['releases'][i]['distro'] == self.plexDistro and self._webData['computer']['Linux']['releases'][i]['build'] == self.plexBuild:
                self.availVersion = self._webData['computer']['Linux']['version']
                self.availURL = self._webData['computer']['Linux']['releases'][i]['url']
                self.availChecksum = self._webData['computer']['Linux']['releases'][i]['checksum']
                self.availFilename = self.plexDownloadDir + "/" + self.availURL.split("/")[-1]
                self.availFixed = self._webData['computer']['Linux']['items_fixed']
                self.availNew = self._webData['computer']['Linux']['items_added']
        return self


    def _upgrade_available(self):
        self.upgradeAvailable = False if self.currentVersion == self.availVersion else True
        return self



def download_file(server):
    if os.path.exists(server.availFilename) and hashlib.sha1(open(server.availFilename, "rb").read()).hexdigest() == server.availChecksum:
        print(f'File already downloaded.')
        downloaded = True
    else:
        count = 0
        while not os.path.exists(server.availFilename) and count <= server.DEFAULT_TIMEOUT:
            print(f'Downloading File: {server.availFilename}. Attempt {count} of {server.DEFAULT_TIMEOUT}.')
            os.makedirs(os.path.dirname(server.availFilename), exist_ok=True)
            r = requests.get(server.availURL, stream=True)
            size_bytes = int(r.headers.get('content-length', 0))
            size_block = 1024
            progress_bar = tqdm.tqdm(total=size_bytes, unit='iB', unit_scale=True)
            with open(server.availFilename, "wb") as file:
                for data in r.iter_content(size_block):
                    progress_bar.update(len(data))
                    file.write(data)
            progress_bar.close()
            print(f'Downloaded - Checking Checksum')
            if hashlib.sha1(open(server.availFilename, "rb").read()).hexdigest() == server.availChecksum:
                downloaded = True
                print(f'Checksum Match')
            else:
                print(f'Checksum mismatch, Bad file')
                downloaded = False
            count += 1
        if count > server.DEFAULT_TIMEOUT:
            downloaded = False
            print(f' There was an issue downloading {server.availFilename}')
    return downloaded


def install_file(filename):
    command = ['/usr/bin/dpkg', '-i', server.availFilename]
    temp_filter = filter(lambda x: x != "", command)
    command = list(temp_filter)
    output = subprocess.run(command, capture_output=True)
    if output.returncode == 0:
        print('Server Upgraded Successfully')
        return True
    else:
        print("Upgrade Failed.")
        print(output)
        return False


def check_root():
    print(f'Running as User: {getpass.getuser()}. UID: {os.getuid()}. Effective UID: {os.geteuid()}')
    if os.getuid() != 0:
        print(f'***This program needs to be run as root to install the package.***\nPackage will be downloaded if newer but not installed.')
    return os.getuid()


def archive_files(server):
    file_list =[]
    print('Archiving Old Package Files')
    for (root, dirs, files) in os.walk(os.path.dirname(server.availFilename), topdown=True):
        for f in files:
            file_name = os.path.join(root, f)
            file_list.append(file_name)
    if server.availFilename in file_list:
        file_list.remove(server.availFilename)
    for i in range(len(file_list)):
        if len(file_list[i]) > 15 and file_list[i].rsplit("/")[-1][0:15] == "plexmediaserver":
            shutil.move(file_list[i], server.plexArchiveDir + "/" + file_list[i].rsplit("/")[-1])


def call_prowl(app_name, server, text,):
    action = ['add', 'verify', 'retrieve_token', 'retrieve_apikey']
    data = {'event': server.name, 'description': text, 'priority': server.prowlPriority,
            'application': app_name, 'apikey': server.prowlApiKey}
    base_url = "https://api.prowlapp.com/publicapi/"
    post_url = base_url + action[0]
    result = requests.post(post_url, data)
    if result.status_code != 200:
        print(f'Error Sending Prowl notification: {prowl_error_code(result)}')
    else:
        print(f'Prowl Notification Sent')
    return result


if __name__ == '__main__':
    server = plexServer(os.uname()[1])
    downloaded = download_file(server)

    if server.upgradeAvailable:
        uid = check_root()
        downloaded = download_file(server)
    else:
        print(f"Server {server.friendlyName} is already running the latest version, nothing to do.")
        downloaded = False
    if downloaded and uid == 0:
        installed = install_file(server)
        if installed:
            call_prowl("PMS Updater", server, "PMS Upgraded Successfully")
            print(f'\nPMS Upgraded')
            print(f'Old Version: {server.currentVersion}')
            print(f'New Version: {server.availVersion}')
            print(f'\nNew Features.\n-------------\n{server.availNew}\n\n')
            print(f'Bug Fixes.\n----------\n{server.availFixed}\n\n')
            archive_files(server)
    print('Script Complete')





