import mysql.connector
import alpaca_trade_api as tradeapi
import threading
import time
import datetime
from datetime import datetime as dt 
import random
import string
import json
import cronus.beat as beat
from collections import deque
updateRate = 2
beat.set_rate(updateRate)

#init alpaca connection
API_KEY = "PKOCPSVQ9AIPDXBKLNQD"
API_SECRET = "uIGUxRsxZd58rCvmn4RQtJgdPtijr8uMqORQcQLq"
APCA_API_BASE_URL = "https://paper-api.alpaca.markets"
alpaca = tradeapi.REST(API_KEY, API_SECRET, APCA_API_BASE_URL, 'v2')


#init database connection
db = mysql.connector.connect(
  host="localhost",
  user="nbury",
  passwd="Lobstero1ogy",
  database="stockdata",
  auth_plugin='mysql_native_password'
)
cursor = db.cursor()


# We only consider stocks with per-share prices inside this range
min_share_price = 1.0
max_share_price = 10.0
# Minimum previous-day dollar volume for a stock we might consider
min_last_dv = 500000
#set tickers
def get_tickers():
        print('Getting current ticker data...')
        tickers = alpaca.polygon.all_tickers()
        print('Success.')
        assets = alpaca.list_assets()
        symbols = [asset.symbol for asset in assets if asset.tradable]
        return [ticker.ticker for ticker in tickers if (
            ticker.ticker in symbols and
            ticker.lastTrade['p'] >= min_share_price and
            ticker.lastTrade['p'] <= max_share_price and
            ticker.prevDay['v'] * ticker.lastTrade['p'] > min_last_dv and
            ticker.todaysChangePerc >= 3.5
        )]
tickers = get_tickers()
recentData = {}
for t in tickers:
    recentData[t] = deque(maxlen = updateRate * 30)


def printProgressBar (iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█', printEnd = "\r"):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end = printEnd)
    # Print New Line on Complete
    if iteration >= total: 
        print()
def awaitMarketOpen():
        isOpen = alpaca.get_clock().is_open
        while(not isOpen):
            clock = alpaca.get_clock()
            openingTime = clock.next_open.replace(tzinfo=datetime.timezone.utc).timestamp()
            currTime = clock.timestamp.replace(tzinfo=datetime.timezone.utc).timestamp()
            timeToOpen = int((openingTime - currTime) / 60)
            print(str(timeToOpen) + " minutes til market open.")
            time.sleep(60)
            isOpen = alpaca.get_clock().is_open

def updateStocks(stocks):
    db = mysql.connector.connect(
    host="localhost",
    user="nbury",
    passwd="Lobstero1ogy",
    database="stockdata",
    auth_plugin='mysql_native_password'
    )
    cursor = db.cursor()
    for stock in stocks:
        recent = recentData[stock]
        quote = alpaca.polygon.last_quote(stock)
        lastPrice = quote.askprice
        t = int(dt.fromisoformat(str(quote.timestamp)).timestamp())

        if( len(list(recent)) < updateRate * 30):
            recent.append(lastPrice)
        else:
            recent.pop()
            recent.append(lastPrice)
        recent = list(recent)
        avg5 = avg10 = avg30 = total = 0
        for i,p in enumerate(recent):
            if(i < updateRate * 5):
                avg5 = avg5 + p
            if(i < updateRate * 10):
                avg10 = avg10 + p
            if(i < updateRate * 30):
                avg30 = avg30 + p   
            total = total + 1
        if total > 5:
            avg5 = avg5 /5
        else:
            avg5 = avg5 / total
        if total > 10:
            avg10 = avg10 /10
        else:
            avg10 = avg10 / total
        avg30 = avg30 / total
        sql = "INSERT INTO stock(stock, date, time, price, avg5, avg10, avg30) VALUES (%s, CURRENT_DATE(), %s, %s, %s, %s, %s);"
        val =(stock,str(t),str(lastPrice),str(avg5),str(avg10),str(avg30))
        cursor.execute(sql, val)
        db.commit()
while True:
    if alpaca.get_clock().is_open:
        waitTime = dt.now() + datetime.timedelta(seconds=30)
        numThreads = 8
        i = 0
        l = len(tickers)
        stocksPerThread = int(l / numThreads)
        threads = []
        while i < l:
            a = tickers[i:min(i+stocksPerThread,l)]
            t = threading.Thread(target=updateStocks, args=([a]))
            threads.append(t)
            i = i+stocksPerThread
        for thread in threads:
            thread.start()
        i = 0
        for thread in threads:
            thread.join()
            i = i + 1
            printProgressBar(i,len(threads))
        print("Stocks Updated at: " +str(dt.now()))
        while dt.now() < waitTime:
            time.sleep(1)
    else:
        awaitMarketOpen()


