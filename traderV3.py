'''
V3 changes
Switch to pandas structure
use macd as main indicator
experiment with other indicators

2 pandas
stocks (stores recent stock data)
    time
    price
    macd vars
portfolio
    stock
    qty
    profit/loss
    time of buy
    buy price
'''
import alpaca_trade_api as tradeapi
import threading
import time
import datetime
import pandas as pd
import ta
from ta.trend import MACD as macd
from datetime import datetime as dt 
import random
import string
import json
import sys
API_KEY = "PKLLR3NL8SH0WF1SQDSS"
API_SECRET = "JzhbXyxHcNOmcadKdLbu70hlgZsnqNzYHiwF/dyQ"
APCA_API_BASE_URL = "https://paper-api.alpaca.markets"
# We only consider stocks with per-share prices inside this range
min_share_price = 1.0
max_share_price = 10.0
# Minimum previous-day dollar volume for a stock we might consider
min_last_dv = 500000
# Stop limit to default to
default_stop = 0
profit_stop = .01
# How much of our portfolio to allocate to any one position
risk = 0.01

def insert(df, row):
    insert_loc = df.index.max()

    if pd.isna(insert_loc):
        df.loc[0] = row
    else:
        df.loc[insert_loc + 1] = row

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

#get all stocks that fit a certain criteria
def get_tickers(alpaca):
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
            ticker.todaysChangePerc >= 2
        )]


class trader:
    def __init__(self):
        self.alpaca = tradeapi.REST(API_KEY, API_SECRET, APCA_API_BASE_URL, 'v2')
        self.account = self.alpaca.get_account()
        print(self.account)
        self.stockList= get_tickers(self.alpaca)
        self.stocks = {}
        self.portfolio = pd.DataFrame(columns = ['qty','pl','buy_time','buy_price'])
        self.allStocks = []
        for stock in self.allStocks:
            self.stocks[stock] = pd.DataFrame(columns = ['price','macdLong','macdShort','macdSignal'])
        
        pos = self.alpaca.list_positions()
        orders = self.alpaca.list_orders(status = 'filled',limit = 500)

        for p in pos:
            #print(p)
            sym = p.symbol
            qty = p.qty
            row = pd.DataFrame(index = [sym], data = [[qty,0,0,0]], columns = ['qty','pl','buy_time','buy_price'])
            self.portfolio = pd.concat([self.portfolio,row])
        for o in orders:
            sym = o.symbol
            time = o.filled_at
            price = o.filled_avg_price
            if sym in self.portfolio.index.values:
                p = self.portfolio.loc[sym]
                p['buy_time'] = time
                p['buy_price'] = price
        self.minutesSinceUpdateStocks = 0
        self.blacklist = set()
        self.timeToClose = None
    
    #pause running until market is open
    def awaitMarketOpen(self):
        isOpen = self.alpaca.get_clock().is_open
        while(not isOpen):
            clock = self.alpaca.get_clock()
            openingTime = clock.next_open.replace(tzinfo=datetime.timezone.utc).timestamp()
            currTime = clock.timestamp.replace(tzinfo=datetime.timezone.utc).timestamp()
            timeToOpen = int((openingTime - currTime) / 60)
            print(str(timeToOpen) + " minutes til market open.")
            time.sleep(60)
            isOpen = self.alpaca.get_clock().is_open

    #create and submit an order
    def submitOrder(self, qty, stock, side, resp): 
        if(qty > 0):
            try:
                order = self.alpaca.submit_order(stock, qty, side, "market", "day")
                print("Market order of | " + str(qty) + " " + stock + " " + side + " | completed.")
                if(side == 'buy'):
                    self.portfolio[stock]['active'] = True
                    self.portfolio[stock]['qty'] = qty
                    self.portfolio[stock]['buy_price'] = order.filled_avg_price
                    self.portfolio['num_active'] = self.portfolio['num_active'] + 1
                else:
                    self.portfolio[stock]['active'] = False
                    self.portfolio[stock]['qty'] = 0
                    self.portfolio['num_active'] = self.portfolio['num_active'] - 1
                    self.portfolio['total_profit_loss'] = self.portfolio['total_profit_loss'] + self.portfolio[stock]['profit_loss']
                    self.portfolio[stock]['profit_loss'] = 0
                resp.append(True)
            except:
                print("Order of | " + str(qty) + " " + stock + " " + side + " | did not go through. ")
                resp.append(False)
        else:
            print("Quantity is 0, order of | " + str(qty) + " " + stock + " " + side + " | not completed. ")
            resp.append(True)

    def updateStockSet(self,stocks):
        for stock in stocks:
            quote = self.alpaca.polygon.last_quote(stock)
            lastPrice = quote.askprice
            timestamp = quote.timestamp
            row = pd.DataFrame(index = [timestamp],data = [[lastPrice,0,0,0]], columns = ['price','macdLong','macdShort','macdSignal'])
            self.stocks[stock] = pd.concat([self.stocks[stock],row])
            prices = self.stocks[stock]['prices']
            m  = macd(prices)
            prices = self.stocks[stock]['macdLong'] = m.macd()
            prices = self.stocks[stock]['macdShort'] = m.macd_diff()
            prices = self.stocks[stock]['macdSignal'] = m.macd_signal()
    #update 10 min percent changes in self.allstocks
    def getStockData(self):
        print("Updating Stocks")
        i = 0
        l = len(self.allStocks)
        threads = []
        while i < l:
            res = 0
            a = self.allStocks[i:min(i+8,l)]
            t = threading.Thread(target=self.updateStockSet, args=([a]))
            threads.append(t)
            i = i+8
        for thread in threads:
            thread.start()
        i = 0
        for thread in threads:
            thread.join()
            i = i + 1
            printProgressBar(i,len(threads))

    def getTotalProfit(self):
        self.account = self.alpaca.get_account() 
        print("Today's Profit/Loss: "+str(float(self.account.equity) - float(self.account.last_equity) ))

    #determine if we should sell a stock
    def sell(self,symbol):
        stock =  self.portfolio[symbol]
        return False

    #determine if we should buy a stock, returns how many
    def buy(self,symbol):
        stock =  self.stocks[symbol]
        if(symbol in self.blacklist or self.portfolio['num_active']>100 or self.sell(symbol)):
            return -1
        alloc = float(self.account.portfolio_value) * risk 
        qty = 1#int( float(self.account.portfolio_value) * risk / stock['last_price'])
        return qty

    #main loop 
    def run(self):
        self.awaitMarketOpen()
        if(len(sys.argv) < 2):
            for i in range(20):
                print("("+str(i+1)+"/20)")
                self.getStockData()
                time.sleep(30)
        else:
            self.getStockData()

        while True:
            #for each stock in our portfolio determine if we should sell it, and remove it from our portfolio if we need to
            resp = []
            for stock in self.allStocks:
                try:
                    if (self.sell(stock)):
                        self.submitOrder(self.portfolio[stock]['qty'],stock,"sell", resp)
                    qty = self.buy(stock)
                    if qty > 0:
                        self.submitOrder(qty,stock,"buy",resp)
                except TypeError:
                    print("Error in list")

            #update clock and time to close
            clock = self.alpaca.get_clock()
            closingTime = clock.next_close.replace(tzinfo=datetime.timezone.utc).timestamp()
            currTime = clock.timestamp.replace(tzinfo=datetime.timezone.utc).timestamp()
            self.timeToClose = closingTime - currTime
            
            if(self.timeToClose < (60 * 5)):
                # Close all positions when 15 minutes til market close.
                print("Market closing soon.  Closing positions.")
                self.blacklist.clear()
                time.sleep(15*60)
                
                self.awaitMarketOpen()
            else:
                #update stock universe if needed and then sleep 60
                self.minutesSinceUpdateStocks = self.minutesSinceUpdateStocks + 1
                if self.minutesSinceUpdateStocks >30:
                    self.allStocks = get_tickers(self.alpaca)
                    for stock in self.stockUniverse:
                        if not any(s == stock for s in self.allStocks):
                            self.allStocks.append([stock])
                            self.stockData[stock] = {'times':[],'prices':[]}
                    self.minutesSinceUpdateStocks = 0  
            self.getTotalProfit()
            print()
            time.sleep(30)
            self.getStockData()
            print()

t = trader()
t.run()