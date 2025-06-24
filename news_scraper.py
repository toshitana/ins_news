import csv
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import os

# グローバル変数としてセレクタ情報を保持
SITE_SELECTORS = {}

def load_selectors(selectors_csv_path="site_selectors.csv"):
    """
    site_selectors.csv からセレクタ情報を読み込み、SITE_SELECTORSグローバル変数に格納する。
    """
    if not os.path.exists(selectors_csv_path):
        print(f"Warning: Selector file '{selectors_csv_path}' not found. Using generic selectors.")
        return

    with open(selectors_csv_path, 'r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # CSVのヘッダーに合わせてキーを調整
            company_name = row.get('会社名')
            if company_name:
                SITE_SELECTORS[company_name] = {
                    'list_selector': row.get('ニュースリスト親要素セレクタ'),
                    'title_selector': row.get('記事タイトルセレクタ'),
                    'date_selector': row.get('日付セレクタ'),
                    'link_selector': row.get('記事リンクセレクタ'),
                }
    print(f"Loaded selectors for {len(SITE_SELECTORS)} companies from '{selectors_csv_path}'.")


def get_news_releases(companies_csv_path, days_within=7):
    """
    CSVファイルから企業のリストを読み込み、指定された日数以内に公開されたニュースリリースを取得します。

    Args:
        companies_csv_path (str): 企業名とニュースリリースページのURLを含むCSVファイルのパス。
        days_within (int): ニュースリリースを検索する過去の日数。

    Returns:
        list: 該当するニュースリリースのリスト。各要素は辞書で、
              {'company': '会社名', 'title': 'ニュースタイトル', 'url': 'ニュースURL'} の形式。
    """
    found_news = []
    today = datetime.now()
    date_limit = today - timedelta(days=days_within)

    with open(companies_csv_path, 'r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            company_name = row['company']
            news_page_url = row['url']

            print(f"Checking {company_name} at {news_page_url}...")

            skipped_sites_log = "skipped_sites.log" # Log file for skipped sites
            try:
                # Add headers to mimic a browser visit, also disable SSL verification for problematic sites
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response = requests.get(news_page_url, timeout=15, headers=headers, verify=False) # Increased timeout and added verify=False
                response.raise_for_status()  # HTTPエラーがあれば例外を発生させる
                soup = BeautifulSoup(response.content, 'html.parser')

                selectors = SITE_SELECTORS.get(company_name)

                if selectors and selectors.get('list_selector') and \
                   selectors.get('title_selector') and \
                   selectors.get('date_selector') and \
                   selectors.get('link_selector') and \
                   not selectors['list_selector'].startswith("SKIPPED"):

                    print(f"  Using specific selectors for {company_name}")
                    news_items = soup.select(selectors['list_selector'])
                    if not news_items:
                        print(f"  DEBUG: No items found with list selector: '{selectors['list_selector']}' for {company_name}")

                    for i, item in enumerate(news_items):
                        print(f"  DEBUG: Processing item {i+1}/{len(news_items)} for {company_name}")
                        title_tag = item.select_one(selectors['title_selector'])

                        date_text_content = "N/A" # 初期化
                        date_text_element = None
                        if not selectors['date_selector'].startswith("REGEX_DATE:"):
                            date_text_element = item.select_one(selectors['date_selector'])
                            if date_text_element:
                                date_text_content = date_text_element.get_text(strip=True)
                            else:
                                print(f"    DEBUG: Date element not found with selector '{selectors['date_selector']}'")
                        else: # REGEX_DATE
                            pattern_str = selectors['date_selector'].split("REGEX_DATE:", 1)[1]
                            item_text_for_regex = item.get_text(separator=" ", strip=True)
                            match_date_in_item = re.search(pattern_str, item_text_for_regex)
                            if match_date_in_item:
                                date_text_content = match_date_in_item.group(0)
                                print(f"    DEBUG: Date matched by REGEX_DATE '{pattern_str}' -> '{date_text_content}' from item text: '{item_text_for_regex[:100]}...'")
                            else:
                                print(f"    DEBUG: Date REGEX_DATE '{pattern_str}' not matched in item text: '{item_text_for_regex[:100]}...'")
                                date_text_content = "N/A_REGEX_FAIL"

                        link_tag = item.select_one(selectors['link_selector'])

                        news_title = title_tag.get_text(strip=True) if title_tag else "N/A"
                        date_text = date_text_content

                        news_url = "N/A"
                        if link_tag:
                            href_val = link_tag.get('href')
                            if href_val:
                                news_url = href_val
                            elif link_tag.name == 'link' and link_tag.get_text(strip=True):
                                news_url = link_tag.get_text(strip=True)

                            if news_url != "N/A" and not news_url.startswith('http'):
                                from urllib.parse import urljoin
                                news_url = urljoin(news_page_url, news_url)

                        print(f"    DEBUG: Raw Extracted -> Title: '{news_title}', Date Text: '{date_text}', URL: '{news_url}'")

                        if news_title != "N/A" and date_text != "N/A" and not date_text.startswith("N/A_") and news_url != "N/A":
                            parsed_date = None

                            # REGEX_DATE の場合、date_text は既に正規表現で抽出された文字列のはず
                            # それ以外の場合、date_text_element.get_text(strip=True) で取得したテキスト

                            # 多様な日付フォーマットに対応するパターンのリスト
                            # 順番が重要。より具体的なもの、または頻出するものを先に。
                            common_date_patterns = [
                                {'regex': re.compile(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日?'), 'format_str': '%Y年%m月%d日'},
                                {'regex': re.compile(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'), 'format_str': '%Y年%m月%d日'},
                                {'regex': re.compile(r'(\d{4})/\s*(\d{1,2})/\s*(\d{1,2})'), 'format_str': '%Y/%m/%d'},
                                {'regex': re.compile(r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})'), 'format_str': '%Y.%m.%d'},
                                {'regex': re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:[+-]\d{2}:\d{2}|Z)?'), 'format_str': '%Y-%m-%dT%H:%M:%S'}, # ISO 8601
                                {'regex': re.compile(r'(\d{4})-(\d{2})-(\d{2})'), 'format_str': '%Y-%m-%d'},
                                # 英語フォーマット (月名は別途処理が必要な場合も)
                                # (例: May 15, 2024 や 15 May, 2024 などはstrptimeで直接パースが難しい場合がある)
                            ]

                            for p_info in common_date_patterns:
                                match = p_info['regex'].search(date_text)
                                if match:
                                    date_str_to_parse = match.group(0)
                                    # 年月日の部分だけを取り出す (T以降は無視するケースなどに対応)
                                    if 'T' in p_info['format_str']: # ISO形式の場合
                                        # date_str_to_parse はYYYY-MM-DDTHH:MM:SSZ などの形式
                                        try:
                                            parsed_date = datetime.fromisoformat(date_str_to_parse.replace('Z', '+00:00'))
                                            break
                                        except ValueError:
                                            # 時刻部分でエラーになる場合があるので、日付部分のみで試す
                                            try:
                                                parsed_date = datetime.strptime(date_str_to_parse.split('T')[0], "%Y-%m-%d")
                                                break
                                            except ValueError:
                                                continue # 次のパターンへ
                                    else: # その他の YMD 形式
                                        # format_str は %Y年%m月%d日 のような形式を期待
                                        # マッチした部分文字列から再構築するより、マッチグループから直接datetimeを作る方が確実
                                        try:
                                            groups = match.groups()
                                            if len(groups) >= 3:
                                                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                                                parsed_date = datetime(year, month, day)
                                                break
                                        except ValueError:
                                            continue # 次のパターンへ

                            # 英語の月名を含む日付の対応 (例: "June 20, 2025", "Jun 20, 2025")
                            if not parsed_date:
                                try:
                                    # 例: "June 20, 2025" や "Jun. 20, 2025"
                                    # 月名は英語のフルネームまたは短縮形、ドットの有無を許容
                                    # 年は4桁、日は1桁または2桁
                                    month_day_year_match = re.search(r'([A-Za-z]{3,})\.?\s+(\d{1,2}),?\s+(\d{4})', date_text)
                                    if month_day_year_match:
                                        month_str, day_str, year_str = month_day_year_match.groups()
                                        # 月名を数値に変換 (よく使われる形式のみ対応)
                                        month_map = {name: num for num, name in enumerate(calendar.month_name) if name}
                                        month_abbr_map = {name: num for num, name in enumerate(calendar.month_abbr) if name}
                                        month_str_cleaned = month_str.capitalize()

                                        month_val = month_map.get(month_str_cleaned) or month_abbr_map.get(month_str_cleaned)
                                        if month_val:
                                            parsed_date = datetime(int(year_str), month_val, int(day_str))
                                except Exception as e_month_parse:
                                    print(f"  English month parsing error for '{date_text}': {e_month_parse}")


                            if parsed_date and parsed_date.date() >= date_limit.date():
                                print(f"  Found (Specific): {news_title} ({parsed_date.strftime('%Y-%m-%d %H:%M:%S') if parsed_date.hour or parsed_date.minute or parsed_date.second else parsed_date.strftime('%Y-%m-%d')})")
                                found_news.append({
                                    'company': company_name,
                                    'title': news_title,
                                    'url': news_url
                                })
                            elif parsed_date:
                                print(f"  Found (Specific, but old): {news_title} ({parsed_date.strftime('%Y-%m-%d')}) / Limit: {date_limit.strftime('%Y-%m-%d')}")
                            else:
                                print(f"  Could not parse date (Specific): '{date_text}' for '{news_title}'")
                        else:
                            print(f"  Missing title, date, or URL using specific selectors for an item in {company_name}. Title: {news_title}, Date Text: {date_text}, URL: {news_url}")

                else: # 特定のセレクタがない、またはスキップ設定の場合
                    if selectors and selectors.get('list_selector', '').startswith("SKIPPED"):
                        print(f"  Skipping {company_name} based on selector config: {selectors['list_selector']}")
                        with open(skipped_sites_log, 'a', encoding='utf-8') as f_log:
                            f_log.write(f"{datetime.now()}: Skipped (Selector Config: {selectors['list_selector']}) - {company_name} - {news_page_url}\n")
                        print("-" * 20)
                        continue # 次の会社へ

                    print(f"  No specific selectors for {company_name} or selectors incomplete. Using generic approach.")
                    # --- ここから各社サイトのHTML構造に合わせたニュース抽出ロジック ---
                    # この部分は汎用的に書くのが非常に難しいため、
                    # 各サイトの構造を個別に解析してセレクタを調整する必要があります。
                    # 以下はいくつかの仮のセレクタの例です。実際のサイトに合わせて変更してください。
                    news_items = soup.select('article.news-item, div.news-list-item, li.news-entry, item, entry') # より多くの可能性をカバー

                    for item in news_items:
                        title_tag = item.select_one('h2, h3, .news-title, .entry-title a, title')
                        date_tag = item.select_one('time, .news-date, .entry-date, pubDate, published')
                        link_tag = item.select_one('a, link') # 最も内側のaタグやlinkタグ

                        if title_tag and date_tag and link_tag:
                            news_title = title_tag.get_text(strip=True)

                            # link_tagがTagオブジェクトの場合とNavigableStringの場合がある
                            if hasattr(link_tag, 'get'):
                                news_url = link_tag.get('href')
                                if news_url is None and link_tag.name == 'link': # RSSフィードのlinkタグなど
                                     news_url = link_tag.get_text(strip=True)
                            else: # NavigableStringの場合（例：<link>http://...</link>）
                                news_url = link_tag.strip()


                            if news_url and not news_url.startswith('http'):
                                # 相対URLを絶対URLに変換
                                from urllib.parse import urljoin
                                news_url = urljoin(news_page_url, news_url)

                            date_text = date_tag.get_text(strip=True)
                            # 日付のパース処理 (様々な形式に対応できるようにする)
                            # 例: "2024年5月15日", "2024/05/15", "2024.05.15", "May 15, 2024"
                            # 正規表現で日付らしき文字列を抽出
                            # より多くの日付形式に対応できるよう改善
                            match = None
                            patterns = [
                                r'(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})日?', # YYYY/MM/DD
                                r'(\d{1,2})\s*([A-Za-z]+)\s*,\s*(\d{4})', # DD Mon, YYYY (e.g., 15 May, 2024)
                                r'([A-Za-z]+)\s*(\d{1,2})\s*,\s*(\d{4})', # Mon DD, YYYY (e.g., May 15, 2024)
                                r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})', # ISO 8601 format
                            ]
                            parsed_date = None
                            for p_idx, pat in enumerate(patterns):
                                match = re.search(pat, date_text)
                                if match:
                                    try:
                                        if p_idx == 0: # YYYY/MM/DD
                                            year, month, day = map(int, match.groups()[:3])
                                            parsed_date = datetime(year, month, day)
                                        elif p_idx == 1: # DD Mon, YYYY
                                            day, month_str, year = match.groups()
                                            month = datetime.strptime(month_str, "%b").month if len(month_str) == 3 else datetime.strptime(month_str, "%B").month
                                            parsed_date = datetime(int(year), month, int(day))
                                        elif p_idx == 2: # Mon DD, YYYY
                                            month_str, day, year = match.groups()
                                            month = datetime.strptime(month_str, "%b").month if len(month_str) == 3 else datetime.strptime(month_str, "%B").month
                                            parsed_date = datetime(int(year), month, int(day))
                                        elif p_idx == 3: # ISO 8601
                                            year, month, day, hour, minute, second = map(int, match.groups()[:6])
                                            parsed_date = datetime(year, month, day, hour, minute, second)
                                        break
                                    except ValueError as ve:
                                        print(f"  Date parsing error for '{date_text}' with pattern '{pat}': {ve}")
                                        continue

                            if parsed_date:
                                if parsed_date >= date_limit:
                                    print(f"  Found (Generic): {news_title} ({parsed_date.strftime('%Y-%m-%d')})")
                                    found_news.append({
                                        'company': company_name,
                                        'title': news_title,
                                        'url': news_url
                                    })
                            else:
                                # 日付が見つからない場合、タイトルやURLに日付が含まれているかチェック (簡易的)
                                if any(str(d) in news_title or str(d) in news_url for d in range(date_limit.day, today.day + 1)) and \
                                   any(str(m) in news_title or str(m) in news_url for m in [date_limit.month, today.month]) and \
                                   str(today.year) in (news_title or news_url): # 年は今年のみを想定
                                    print(f"  Found (Generic - date inferred): {news_title}")
                                    found_news.append({
                                        'company': company_name,
                                        'title': news_title,
                                        'url': news_url
                                    })
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    print(f"Skipping {company_name} ({news_page_url}) due to 403 Forbidden.")
                    with open(skipped_sites_log, 'a', encoding='utf-8') as f_log:
                        f_log.write(f"{datetime.now()}: Skipped (403 Forbidden) - {company_name} - {news_page_url}\n")
                else:
                    print(f"HTTP Error for {company_name} ({news_page_url}): {e}")
                    with open(skipped_sites_log, 'a', encoding='utf-8') as f_log:
                        f_log.write(f"{datetime.now()}: Skipped (HTTP Error: {e.response.status_code}) - {company_name} - {news_page_url}\n")
            except requests.exceptions.SSLError as e:
                print(f"Skipping {company_name} ({news_page_url}) due to SSL Error: {e}")
                with open(skipped_sites_log, 'a', encoding='utf-8') as f_log:
                    f_log.write(f"{datetime.now()}: Skipped (SSL Error) - {company_name} - {news_page_url}\n")
            except requests.exceptions.Timeout as e:
                print(f"Skipping {company_name} ({news_page_url}) due to Timeout: {e}")
                with open(skipped_sites_log, 'a', encoding='utf-8') as f_log:
                    f_log.write(f"{datetime.now()}: Skipped (Timeout) - {company_name} - {news_page_url}\n")
            except requests.exceptions.RequestException as e:
                print(f"Error fetching {news_page_url}: {e}")
                with open(skipped_sites_log, 'a', encoding='utf-8') as f_log:
                    f_log.write(f"{datetime.now()}: Skipped (RequestException: {type(e).__name__}) - {company_name} - {news_page_url}\n")
            except Exception as e:
                print(f"Error processing {company_name} ({news_page_url}): {e}")
                with open(skipped_sites_log, 'a', encoding='utf-8') as f_log:
                    f_log.write(f"{datetime.now()}: Skipped (Other Exception: {type(e).__name__}) - {company_name} - {news_page_url} - {e}\n")
            print("-" * 20)
    return found_news

def save_to_csv(news_list, output_filename):
    """
    ニュースリリースのリストをCSVファイルに保存します。

    Args:
        news_list (list): ニュースリリースの辞書のリスト。
        output_filename (str): 出力するCSVファイル名。
    """
    if not news_list:
        print("No news releases found to save.")
        return

    keys = news_list[0].keys()
    with open(output_filename, 'w', newline='', encoding='utf-8-sig') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(news_list)
    print(f"News releases saved to {output_filename}")

if __name__ == "__main__":
    companies_file = "companies.csv"
    days = 7 # デフォルト7日間

    # try:
    #     # Script is run by an agent, so direct input is not possible.
    #     # If user wants to specify days, they should modify the 'days' variable directly
    #     # or this script needs to be adapted to take command line arguments.
    #     # days_input = input(f"Enter number of days to check within (default {days}): ")
    #     # if days_input:
    #     #     days = int(days_input)
    # except ValueError:
    #     print(f"Invalid input for days, using default {days} days.")

    load_selectors() # セレクタ情報をロード

    today_str = datetime.now().strftime("%Y_%m_%d")
    # Corrected date range for "within N days":
    # If today is D, and N=7, we want news from D-6, D-5, ..., D.
    # So the start date of the range is today - (N-1) days.
    past_date_str = (datetime.now() - timedelta(days=days-1)).strftime("%Y_%m_%d")
    output_csv_filename = f"{past_date_str}-{today_str}.csv"


    print(f"Checking for news within the last {days} days...")
    recent_news = get_news_releases(companies_file, days)

    if recent_news:
        save_to_csv(recent_news, output_csv_filename)
    else:
        print("No recent news found for any company.")
