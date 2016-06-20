import os
import requests
import vimeo


class VimeoDownloader(object):
    def __init__(self, platform, file_process_handler, logdb, tempfile):
        self.platform = platform
        self.file_process_handler = file_process_handler
        self.logdb = logdb
        self.tempfile = tempfile if tempfile else 'tempfile_{0}.mp4'.format(platform)

        self.credentials = dict(
            key=os.environ[
                "vimeo_{0:s}_client_id".format(platform).upper()],
            secret=os.environ[
                "vimeo_{0:s}_client_secret".format(platform).upper()],
            token=os.environ[
                "vimeo_{0:s}_access_token".format(platform).upper()])

        self.client = vimeo.VimeoClient(**self.credentials)

    def iterate_pages(self, per_page=25):
        next_page = '/me/videos?per_page={0}&page=1&fields=files,uri'.format(
            per_page)
        next_page = self.download_page(next_page)
        while next_page:
            next_page = self.download_page(next_page)

    def download_page(self, page):
        current_result = self.client.get(page).json()

        page_id = 'page-{0}'.format(current_result['page'])
        self.logdb[page_id] = {}

        for files_info in current_result['data']:
            if not len(files_info['files']):
                continue

            vimeo_id = str(files_info['uri'].split('/')[-1])
            file_info = max(files_info['files'], key=lambda x: x['size'])
            self.download_file(file_info['link'], vimeo_id)
            self.logdb[page_id][vimeo_id] = file_info

        return current_result['paging']['next']

    def download_file(self, source_url, vimeo_id):
        response = requests.get(source_url, stream=True)
        with open(self.tempfile, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        self.file_process_handler(vimeo_id, self.tempfile)
