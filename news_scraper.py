import csv
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re

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

                # --- ここから各社サイトのHTML構造に合わせたニュース抽出ロジック ---
                # この部分は汎用的に書くのが非常に難しいため、
                # 各サイトの構造を個別に解析してセレクタを調整する必要があります。
                # 以下はいくつかの仮のセレクタの例です。実際のサイトに合わせて変更してください。

                # 例1: ニュースが <article> タグで囲まれ、日付が <time> タグにある場合
                news_items = soup.select('article.news-item, div.news-list-item, li.news-entry') # より多くの可能性をカバー

                for item in news_items:
                    title_tag = item.select_one('h2, h3, .news-title, .entry-title a')
                    date_tag = item.select_one('time, .news-date, .entry-date')
                    link_tag = item.select_one('a') # 最も内側のaタグを取得しようと試みる

                    if title_tag and date_tag and link_tag:
                        news_title = title_tag.get_text(strip=True)
                        news_url = link_tag.get('href')
                        if news_url and not news_url.startswith('http'):
                            # 相対URLを絶対URLに変換
                            from urllib.parse import urljoin
                            news_url = urljoin(news_page_url, news_url)

                        date_text = date_tag.get_text(strip=True)
                        # 日付のパース処理 (様々な形式に対応できるようにする)
                        # 例: "2024年5月15日", "2024/05/15", "2024.05.15", "May 15, 2024"
                        # 正規表現で日付らしき文字列を抽出
                        match = re.search(r'(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})日?', date_text)
                        if match:
                            year, month, day = map(int, match.groups())
                            try:
                                news_date = datetime(year, month, day)
                                if news_date >= date_limit:
                                    print(f"  Found: {news_title} ({news_date.strftime('%Y-%m-%d')})")
                                    found_news.append({
                                        'company': company_name,
                                        'title': news_title,
                                        'url': news_url
                                    })
                            except ValueError:
                                print(f"  Could not parse date: {date_text}")
                        else:
                            # 日付が見つからない場合、タイトルやURLに日付が含まれているかチェック (簡易的)
                            if any(str(d) in news_title or str(d) in news_url for d in range(date_limit.day, today.day + 1)) and \
                               any(str(m) in news_title or str(m) in news_url for m in [date_limit.month, today.month]) and \
                               str(today.year) in (news_title or news_url): # 年は今年のみを想定
                                print(f"  Found (date inferred): {news_title}")
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
