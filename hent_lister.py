# encoding=utf-8
from __future__ import print_function
import os
import sys
from requests import Session
from requests import HTTPError
import untangle
from textwrap import dedent
import yaml
import time
from tqdm import tqdm
from datetime import datetime
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from xml.sax._exceptions import SAXParseException


if sys.version_info[0] < 3:
    print('This script requires Python 3')
    exit()

def requests_retry_session(
    retries=10,
    backoff_factor=0.3,
    status_forcelist=(400, 500, 502, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def store_report(session, stream, endpoint, report, filter, fields):
    token = None
    aggs = {}
    n = 0
    column_map = {}
    for k, v in enumerate(fields):
        column_map['Column%d' % (k + 1)] = v

    buffer = []
    with tqdm(file=sys.stdout) as pbar:
        while True:
            if token is None:
                params = {'path': report['path'], 'limit': 200, 'filter': filter}
            else:
                params = {'token': token}
            res = session.get(endpoint, params=params)

            xml = untangle.parse(res.text)
            if 'web_service_result' in dir(xml):
                raise RuntimeError(xml.web_service_result.errorList.error.errorMessage.cdata)

            if 'rowset' in dir(xml.report.QueryResult.ResultXml):
                # Sometimes you can get a response with no rows, just a resumption token.
                # perhaps because the server is busy or something.
                if 'Row' in dir(xml.report.QueryResult.ResultXml.rowset):
                    # And sometimes empty rowsets of course...
                    for row in xml.report.QueryResult.ResultXml.rowset.Row:
                        data = {}
                        for k, v in column_map.items():
                            data[v] = ''
                            if k in dir(row):
                                data[v] = getattr(row, k).cdata
                        if data['barcode'] == '':
                            continue
                        if data['callcode'] == 'Unknown':
                            data['callcode'] = '?'
                        if len(data['title']) > 100:
                            data['title'] = data['title'][:98] + '...'
                        buffer.append(data)
                        n += 1
                        aggs[data['process_type']] = aggs.get(data['process_type'], 0) + 1
                        pbar.update(1)

            if 'ResumptionToken' in dir(xml.report.QueryResult):
                token = xml.report.QueryResult.ResumptionToken.cdata

            if xml.report.QueryResult.IsFinished.cdata != 'false':
                break

    buffer = sorted(buffer, key=lambda x: x[report['sort_by']])
    for line in buffer:
        line = report['format'].format(**line).encode('utf-8')
        stream.write(line + '\r\n'.encode('utf-8'))

    return aggs


def main():

    now = datetime.now().strftime('%Y-%m-%d')
    print('Starting: %s' % now)

    # Read config
    with open(os.path.join(os.path.dirname(__file__), 'config.yml')) as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)

    # HTTP session
    api_key = config['alma_api_key']  # Use read-only key
    endpoint = 'https://api-eu.hosted.exlibrisgroup.com/almaws/v1/analytics/reports'
    session = Session()
    session.headers.update({'Authorization': 'apikey ' + api_key})
    session = requests_retry_session(session=session)

    for report in config['reports']:

        report_path = report['path']
        varname = report.get('variable')

        files = report['files']
        if isinstance(files, str):
            files = {files: None}

        for fname, values in files.items():

            if values is None:
                report_filter = None
            else:
                values = ''.join(['<sawx:expr xsi:type="xsd:string">{}</sawx:expr>'.format(value) for value in values])
                report_filter = dedent(
                """<sawx:expr xsi:type="sawx:list" op="in"
                     xmlns:saw="com.siebel.analytics.web/report/v1.1" 
                     xmlns:sawx="com.siebel.analytics.web/expression/v1.1"
                     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
                     xmlns:xsd="http://www.w3.org/2001/XMLSchema">
                       <sawx:expr xsi:type="sawx:sqlExpression">{}</sawx:expr>
                       {}
                   </sawx:expr>""".format(varname, values))

            dest_path = config['dest_path']
            file_path = os.path.join(dest_path, fname)
            print('Updating {}'.format(file_path))
            attempt = 0
            while True:
                try:
                    attempt += 1
                    if attempt > 10:
                        print('Too many failures, exiting')
                        break
                    with open(file_path + '.tmp', 'wb+') as f:
                        aggs = store_report(session, f, endpoint, report, report_filter, report['fields'])
                    os.rename(file_path + '.tmp', file_path)
                    break
                except SAXParseException:
                    pass

            # Store stats so we can plot trends over time
            stats_path = os.path.join(dest_path, 'stats.csv')
            log_path = os.path.join(dest_path, fname + '.log')
            now = datetime.now().strftime('%Y-%m-%d')
            with open(stats_path, 'ab') as f:
                with open(log_path, 'wb') as f2:
                    for k, v in aggs.items():
                        print(' - {}: {}'.format(k, v))
                        f.write('{},{},{},{}\n'.format(now, fname, k, v).encode('utf-8'))
                        f2.write(' - {}: {}\r\n'.format(k, v).encode('utf-8'))

main()

