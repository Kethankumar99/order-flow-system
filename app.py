import requests
import time
import json
import csv
import os
from datetime import datetime, timedelta
from collections import defaultdict
from twilio.rest import Client
import config

# ============================================================
# TWILIO ALERT FUNCTION
# ============================================================
def send_alert(message, alert_type="INFO"):
    """Send WhatsApp alert via Twilio"""
    try:
        client = Client(config.TWILIO_SID, config.TWILIO_TOKEN)
        msg = client.messages.create(
            body=f"🔔 {alert_type}\n\n{message}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n📊 System: Order Flow Monitor",
            from_=config.TWILIO_WHATSAPP_FROM,
            to=config.WHATSAPP_TO
        )
        print(f"✅ WhatsApp sent: {msg.sid}")
        return True
    except Exception as e:
        print(f"❌ Alert failed: {e}")
        return False

# ============================================================
# MAIN SYSTEM
# ============================================================
class ProfessionalOrderFlowSystem:
    def __init__(self, symbol='BTCUSDT'):
        self.symbol = symbol
        self.mirror = "https://data-api.binance.vision"
        self.last_trade_id = None
        self.is_running = True
        
        # Block data
        self.block_trades = []
        self.block_start = None
        self.block_end = None
        self.current_block_id = 0
        
        # Cumulative delta
        self.cumulative_delta = 0.0
        self.cumulative_delta_history = []
        
        # Price history
        self.price_history = []
        self.delta_history = []
        
        # Trade state
        self.in_position = False
        self.entry_price = 0.0
        self.tp1_price = 0.0
        self.tp2_price = 0.0
        self.sl_price = 0.0
        self.position_size = 0.0
        self.entry_time = None
        
        # Trade tracking
        self.trades_history = []
        self.current_trade = {}
        self.last_alert_time = None
        
        # CSV logging
        self.csv_file = f"professional_flow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.trades_csv = f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.init_csv()
        self.init_trades_csv()
        
        # Send startup alert
        send_alert(f"""🚀 SYSTEM STARTED SUCCESSFULLY!

📊 Symbol: {self.symbol}
⏰ Block Duration: {config.BLOCK_MINUTES} minutes
📡 Status: CONNECTED & RUNNING

✅ System is now monitoring BTCUSDT
✅ Alert notifications are ENABLED
✅ Data logging is ACTIVE

You will receive alerts when:
• BUY/SIGNALS detected
• Whale activity detected
• Iceberg orders detected
• Position updates

🟢 SYSTEM READY for market analysis!""", "🚀 STARTUP")

    def init_csv(self):
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'block_id', 'block_start', 'block_end',
                'buy_volume', 'sell_volume', 'total_volume',
                'buy_count', 'sell_count', 'total_trades',
                'order_flow_delta', 'cumulative_delta',
                'buy_pressure', 'sell_pressure',
                'vwap', 'avg_price', 'min_price', 'max_price',
                'poc_price', 'poc_volume',
                'flow_velocity', 'large_trades', 'whale_volume',
                'iceberg_detected', 'absorption',
                'delta_divergence', 'sentiment',
                'market_state', 'verdict', 'confidence', 'reason',
                'in_position', 'entry_price', 'tp1', 'tp2', 'sl'
            ])

    def init_trades_csv(self):
        with open(self.trades_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'trade_id', 'entry_time', 'entry_price',
                'exit_time', 'exit_price', 'position_size',
                'profit_usd', 'profit_percent', 'status'
            ])

    def get_new_trades(self):
        try:
            url = f"{self.mirror}/api/v3/trades"
            params = {'symbol': self.symbol, 'limit': 1000}
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                trades = response.json()
                trades.sort(key=lambda x: x['id'])
                
                new_trades = []
                for trade in trades:
                    if self.last_trade_id is None or trade['id'] > self.last_trade_id:
                        new_trades.append(trade)
                
                if new_trades:
                    self.last_trade_id = new_trades[-1]['id']
                return new_trades
        except Exception as e:
            print(f"⚠️ Error: {e}")
        return []

    def categorize_trade(self, trade):
        price = float(trade['price'])
        qty = float(trade['qty'])
        is_buyer_maker = trade['isBuyerMaker']
        timestamp = datetime.fromtimestamp(trade['time'] / 1000)
        
        if not is_buyer_maker:
            return {'side': 'BUY', 'price': price, 'qty': qty, 'timestamp': timestamp}
        else:
            return {'side': 'SELL', 'price': price, 'qty': qty, 'timestamp': timestamp}

    def get_next_block(self, current_time):
        minute = current_time.minute
        start_minute = (minute // config.BLOCK_MINUTES) * config.BLOCK_MINUTES
        
        block_start = current_time.replace(minute=start_minute, second=0, microsecond=0)
        if current_time >= block_start + timedelta(minutes=config.BLOCK_MINUTES):
            block_start = block_start + timedelta(minutes=config.BLOCK_MINUTES)
        
        block_end = block_start + timedelta(minutes=config.BLOCK_MINUTES)
        return block_start, block_end

    def calculate_vwap(self, trades):
        total_value = sum([t['price'] * t['qty'] for t in trades])
        total_volume = sum([t['qty'] for t in trades])
        return total_value / total_volume if total_volume > 0 else 0

    def calculate_volume_profile(self, trades):
        if not trades:
            return None, None, None
        
        price_volume = defaultdict(float)
        for t in trades:
            price = round(t['price'], 0)
            price_volume[price] += t['qty']
        
        if not price_volume:
            return None, None, None
        
        poc_price = max(price_volume, key=price_volume.get)
        poc_volume = price_volume[poc_price]
        
        sorted_items = sorted(price_volume.items(), key=lambda x: x[1], reverse=True)
        total_vol = sum(price_volume.values())
        cum_vol = 0
        value_area_prices = []
        
        for price, vol in sorted_items:
            cum_vol += vol
            value_area_prices.append(price)
            if cum_vol >= total_vol * 0.7:
                break
        
        value_area_low = min(value_area_prices)
        value_area_high = max(value_area_prices)
        
        return poc_price, poc_volume, (value_area_low, value_area_high)

    def detect_iceberg(self, trades):
        if len(trades) < 10:
            return False
        
        price_groups = defaultdict(list)
        for t in trades:
            price = round(t['price'], 2)
            price_groups[price].append(t)
        
        for price, group in price_groups.items():
            if len(group) >= 5:
                buys = sum(1 for t in group if t['side'] == 'BUY')
                sells = len(group) - buys
                
                if buys / len(group) > 0.8 or sells / len(group) > 0.8:
                    avg_qty = sum(t['qty'] for t in group) / len(group)
                    if avg_qty < 0.02:
                        return True
        return False

    def detect_absorption(self, trades):
        if len(trades) < 20:
            return 'NONE'
        
        recent = trades[-20:]
        buys = [t for t in recent if t['side'] == 'BUY']
        sells = [t for t in recent if t['side'] == 'SELL']
        
        if not buys or not sells:
            return 'NONE'
        
        total_buy = sum(t['qty'] for t in buys)
        total_sell = sum(t['qty'] for t in sells)
        
        if len(buys) < len(sells) and total_buy > total_sell * 2:
            return 'BUY_ABSORPTION'
        elif len(sells) < len(buys) and total_sell > total_buy * 2:
            return 'SELL_ABSORPTION'
        
        return 'NONE'

    def detect_large_trades(self, trades):
        large_trades = []
        whale_volume = 0
        
        for t in trades:
            if t['qty'] >= 2.0:
                large_trades.append(t)
                whale_volume += t['qty']
        
        return large_trades, whale_volume

    def calculate_delta_divergence(self, current_price, current_delta):
        self.price_history.append(current_price)
        self.delta_history.append(current_delta)
        
        if len(self.price_history) > 50:
            self.price_history.pop(0)
            self.delta_history.pop(0)
        
        if len(self.price_history) < 20:
            return 'INSUFFICIENT_DATA'
        
        price_trend = self.price_history[-1] - self.price_history[0]
        delta_trend = self.delta_history[-1] - self.delta_history[0]
        
        if price_trend > 0 and delta_trend < -0.5:
            return 'BEARISH_DIVERGENCE'
        elif price_trend < 0 and delta_trend > 0.5:
            return 'BULLISH_DIVERGENCE'
        elif price_trend > 0 and delta_trend > 0.5:
            return 'CONFIRMATION'
        elif price_trend < 0 and delta_trend < -0.5:
            return 'CONFIRMATION'
        else:
            return 'NEUTRAL'

    def calculate_block_metrics(self):
        if not self.block_trades:
            return None
        
        total_buys = sum([t['qty'] for t in self.block_trades if t['side'] == 'BUY'])
        total_sells = sum([t['qty'] for t in self.block_trades if t['side'] == 'SELL'])
        total_volume = total_buys + total_sells
        buy_count = len([t for t in self.block_trades if t['side'] == 'BUY'])
        sell_count = len([t for t in self.block_trades if t['side'] == 'SELL'])
        prices = [t['price'] for t in self.block_trades]
        
        if total_volume == 0:
            return None
        
        delta = total_buys - total_sells
        self.cumulative_delta += delta
        self.cumulative_delta_history.append(self.cumulative_delta)
        
        buy_pressure = (total_buys / total_volume) * 100
        sell_pressure = (total_sells / total_volume) * 100
        
        vwap = self.calculate_vwap(self.block_trades)
        poc_price, poc_volume, value_area = self.calculate_volume_profile(self.block_trades)
        
        if len(self.block_trades) > 1:
            time_diff = (self.block_trades[-1]['timestamp'] - self.block_trades[0]['timestamp']).total_seconds()
            flow_velocity = len(self.block_trades) / max(time_diff, 1)
        else:
            flow_velocity = 0
        
        large_trades, whale_volume = self.detect_large_trades(self.block_trades)
        iceberg_detected = self.detect_iceberg(self.block_trades)
        absorption = self.detect_absorption(self.block_trades)
        
        avg_price = sum(prices) / len(prices)
        divergence = self.calculate_delta_divergence(avg_price, delta)
        
        if buy_pressure > 70:
            sentiment = 'BULLISH'
        elif buy_pressure < 30:
            sentiment = 'BEARISH'
        else:
            sentiment = 'NEUTRAL'
        
        return {
            'delta': delta,
            'cumulative_delta': self.cumulative_delta,
            'buy_pressure': buy_pressure,
            'sell_pressure': sell_pressure,
            'total_buys': total_buys,
            'total_sells': total_sells,
            'total_volume': total_volume,
            'buy_count': buy_count,
            'sell_count': sell_count,
            'total_trades': len(self.block_trades),
            'avg_price': avg_price,
            'min_price': min(prices),
            'max_price': max(prices),
            'vwap': vwap,
            'poc_price': poc_price,
            'poc_volume': poc_volume,
            'value_area': value_area,
            'flow_velocity': flow_velocity,
            'large_trades': len(large_trades),
            'whale_volume': whale_volume,
            'whale_trades': large_trades,
            'iceberg_detected': iceberg_detected,
            'absorption': absorption,
            'divergence': divergence,
            'sentiment': sentiment
        }

    def check_buy_conditions(self, metrics, previous_metrics):
        if metrics is None or previous_metrics is None:
            return False, []
        
        conditions = []
        
        if previous_metrics['whale_volume'] > 20:
            price_drop = (previous_metrics['avg_price'] - metrics['avg_price']) / previous_metrics['avg_price'] * 100
            if price_drop < 0.3:
                conditions.append(('Whale Dump Failed', True))
            else:
                conditions.append(('Whale Dump Failed', False))
        else:
            conditions.append(('Whale Dump Failed', False))
        
        if len(self.block_trades) > 0:
            current_price = metrics['avg_price']
            dump_price = previous_metrics['avg_price']
            if current_price >= dump_price * 0.997:
                conditions.append(('Price Recovery', True))
            else:
                conditions.append(('Price Recovery', False))
        else:
            conditions.append(('Price Recovery', False))
        
        if previous_metrics['delta'] < 0 and metrics['delta'] > 0:
            conditions.append(('Delta Turn', True))
        else:
            conditions.append(('Delta Turn', False))
        
        if metrics['buy_pressure'] > 60:
            conditions.append(('Buy Pressure > 60%', True))
        else:
            conditions.append(('Buy Pressure > 60%', False))
        
        if metrics['cumulative_delta'] > 20:
            conditions.append(('Cumulative Delta > +20', True))
        else:
            conditions.append(('Cumulative Delta > +20', False))
        
        if metrics['value_area']:
            value_area_low = metrics['value_area'][0]
            if metrics['avg_price'] > value_area_low:
                conditions.append(('Support Hold', True))
            else:
                conditions.append(('Support Hold', False))
        else:
            conditions.append(('Support Hold', False))
        
        if metrics['iceberg_detected']:
            conditions.append(('Iceberg Active', True))
        else:
            conditions.append(('Iceberg Active', False))
        
        all_met = all([c[1] for c in conditions])
        return all_met, conditions

    def check_sell_conditions(self, metrics, previous_metrics):
        if metrics is None or previous_metrics is None:
            return False, []
        
        conditions = []
        
        if len(self.price_history) > 10:
            recent_highs = self.price_history[-10:]
            if metrics['avg_price'] > max(recent_highs) * 0.995:
                conditions.append(('Price Rejection', True))
            else:
                conditions.append(('Price Rejection', False))
        else:
            conditions.append(('Price Rejection', False))
        
        if previous_metrics['delta'] > 0 and metrics['delta'] < 0:
            conditions.append(('Delta Turn', True))
        else:
            conditions.append(('Delta Turn', False))
        
        if metrics['sell_pressure'] > 60:
            conditions.append(('Sell Pressure > 60%', True))
        else:
            conditions.append(('Sell Pressure > 60%', False))
        
        if metrics['cumulative_delta'] < -20:
            conditions.append(('Cumulative Delta < -20', True))
        else:
            conditions.append(('Cumulative Delta < -20', False))
        
        if metrics['value_area']:
            value_area_high = metrics['value_area'][1]
            if metrics['avg_price'] < value_area_high:
                conditions.append(('Resistance Hold', True))
            else:
                conditions.append(('Resistance Hold', False))
        else:
            conditions.append(('Resistance Hold', False))
        
        if metrics['whale_volume'] > 20:
            conditions.append(('Whale Activity', True))
        else:
            conditions.append(('Whale Activity', False))
        
        if metrics['absorption'] == 'SELL_ABSORPTION':
            conditions.append(('Sell Absorption', True))
        else:
            conditions.append(('Sell Absorption', False))
        
        all_met = all([c[1] for c in conditions])
        return all_met, conditions

    def check_exit_conditions(self, metrics):
        if not self.in_position:
            return False, []
        
        conditions = []
        
        if self.entry_price > 0:
            profit_percent = (metrics['avg_price'] - self.entry_price) / self.entry_price * 100
            if profit_percent >= 2.0:
                conditions.append(('TP1 Hit (2%)', True))
            else:
                conditions.append(('TP1 Hit (2%)', False))
            
            if profit_percent >= 4.0:
                conditions.append(('TP2 Hit (4%)', True))
            else:
                conditions.append(('TP2 Hit (4%)', False))
            
            loss_percent = (self.entry_price - metrics['avg_price']) / self.entry_price * 100
            if loss_percent >= 1.0:
                conditions.append(('SL Hit (1%)', True))
            else:
                conditions.append(('SL Hit (1%)', False))
        
        if metrics['divergence'] == 'BEARISH_DIVERGENCE':
            conditions.append(('Bearish Divergence', True))
        else:
            conditions.append(('Bearish Divergence', False))
        
        if metrics['whale_volume'] > 20 and metrics['sell_pressure'] > 60:
            conditions.append(('Whale Distribution', True))
        else:
            conditions.append(('Whale Distribution', False))
        
        if metrics['absorption'] == 'SELL_ABSORPTION':
            conditions.append(('Sell Absorption', True))
        else:
            conditions.append(('Sell Absorption', False))
        
        any_met = any([c[1] for c in conditions])
        return any_met, conditions

    def execute_buy(self, price, metrics):
        if self.in_position:
            return
        
        position_size = 1.0
        self.in_position = True
        self.entry_price = price
        self.position_size = position_size
        self.entry_time = datetime.now()
        
        self.tp1_price = price * 1.02
        self.tp2_price = price * 1.04
        self.sl_price = price * 0.99
        
        self.current_trade = {
            'type': 'BUY',
            'entry_time': self.entry_time,
            'entry_price': self.entry_price,
            'position_size': position_size,
            'tp1': self.tp1_price,
            'tp2': self.tp2_price,
            'sl': self.sl_price
        }
        
        # Send WhatsApp Alert
        message = f"""🟢 BUY SIGNAL EXECUTED!

💰 Entry Price: ${self.entry_price:.2f}
📊 Position Size: {position_size:.1f}% of capital

🎯 Take Profit 1: ${self.tp1_price:.2f} (+2.0%)
🎯 Take Profit 2: ${self.tp2_price:.2f} (+4.0%)
🛑 Stop Loss: ${self.sl_price:.2f} (-1.0%)

📈 Buy Pressure: {metrics['buy_pressure']:.1f}%
📊 Cumulative Delta: {metrics['cumulative_delta']:.2f}
🐋 Whale Volume: {metrics['whale_volume']:.2f} BTC

⚠️ Trade is SIMULATED - No real funds used!"""
        
        send_alert(message, "🟢 BUY SIGNAL")

    def execute_sell(self, price, metrics):
        if self.in_position:
            return
        
        position_size = 1.0
        self.in_position = True
        self.entry_price = price
        self.position_size = position_size
        self.entry_time = datetime.now()
        
        self.tp1_price = price * 0.98
        self.tp2_price = price * 0.96
        self.sl_price = price * 1.01
        
        self.current_trade = {
            'type': 'SELL',
            'entry_time': self.entry_time,
            'entry_price': self.entry_price,
            'position_size': position_size,
            'tp1': self.tp1_price,
            'tp2': self.tp2_price,
            'sl': self.sl_price
        }
        
        # Send WhatsApp Alert
        message = f"""🔴 SELL SIGNAL EXECUTED!

💰 Entry Price: ${self.entry_price:.2f}
📊 Position Size: {position_size:.1f}% of capital

🎯 Take Profit 1: ${self.tp1_price:.2f} (+2.0%)
🎯 Take Profit 2: ${self.tp2_price:.2f} (+4.0%)
🛑 Stop Loss: ${self.sl_price:.2f} (-1.0%)

📈 Sell Pressure: {metrics['sell_pressure']:.1f}%
📊 Cumulative Delta: {metrics['cumulative_delta']:.2f}
🐋 Whale Volume: {metrics['whale_volume']:.2f} BTC

⚠️ Trade is SIMULATED - No real funds used!"""
        
        send_alert(message, "🔴 SELL SIGNAL")

    def execute_exit(self, price, reason, metrics):
        if not self.in_position:
            return
        
        profit_percent = (price - self.entry_price) / self.entry_price * 100
        profit_usd = (price - self.entry_price) * self.position_size
        
        self.exit_time = datetime.now()
        
        # Send WhatsApp Alert
        message = f"""🟡 POSITION EXITED!

💰 Exit Price: ${price:.2f}
📊 Profit: ${profit_usd:.2f} ({profit_percent:+.2f}%)

💡 Reason: {reason}

📈 Entry: ${self.entry_price:.2f}
📊 Position Size: {self.position_size:.1f}%

📉 Cumulative Delta: {metrics['cumulative_delta']:.2f}
🔄 Market State: {metrics['sentiment']}"""
        
        send_alert(message, "🟡 EXIT SIGNAL")
        
        # Save trade
        with open(self.trades_csv, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                len(self.trades_history) + 1,
                self.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
                round(self.entry_price, 2),
                self.exit_time.strftime('%Y-%m-%d %H:%M:%S'),
                round(price, 2),
                self.position_size,
                round(profit_usd, 2),
                round(profit_percent, 2),
                'COMPLETED'
            ])
        
        self.trades_history.append({
            'entry_time': self.entry_time,
            'entry_price': self.entry_price,
            'exit_time': self.exit_time,
            'exit_price': price,
            'profit_usd': profit_usd,
            'profit_percent': profit_percent
        })
        
        self.in_position = False
        self.entry_price = 0.0
        self.tp1_price = 0.0
        self.tp2_price = 0.0
        self.sl_price = 0.0
        self.position_size = 0.0
        self.entry_time = None
        self.current_trade = {}

    def generate_signal(self, metrics, previous_metrics):
        if metrics is None:
            return {'verdict': 'HOLD_FLAT', 'state': 'RETAIL_NOISE', 'confidence': 1, 'reason': 'No data'}
        
        buy_met, buy_conditions = self.check_buy_conditions(metrics, previous_metrics)
        sell_met, sell_conditions = self.check_sell_conditions(metrics, previous_metrics)
        exit_met, exit_conditions = self.check_exit_conditions(metrics)
        
        if self.in_position and exit_met:
            reason = ' | '.join([c[0] for c in exit_conditions if c[1]])
            return {
                'verdict': 'EXIT_POSITION',
                'state': 'EXITING',
                'confidence': 9,
                'reason': reason,
                'conditions': exit_conditions
            }
        
        if buy_met and not self.in_position:
            reason = ' | '.join([c[0] for c in buy_conditions if c[1]])
            return {
                'verdict': 'EXECUTE_MARKET_BUY',
                'state': 'AGGRESSIVE_ACCUMULATION',
                'confidence': 9,
                'reason': reason,
                'conditions': buy_conditions
            }
        
        if sell_met and not self.in_position:
            reason = ' | '.join([c[0] for c in sell_conditions if c[1]])
            return {
                'verdict': 'EXECUTE_MARKET_SELL',
                'state': 'AGGRESSIVE_DISTRIBUTION',
                'confidence': 9,
                'reason': reason,
                'conditions': sell_conditions
            }
        
        return {
            'verdict': 'HOLD_FLAT',
            'state': 'RETAIL_NOISE',
            'confidence': 5,
            'reason': 'Conditions not met',
            'conditions': []
        }

    def process_block(self, previous_metrics):
        metrics = self.calculate_block_metrics()
        if metrics is None:
            return
        
        signal = self.generate_signal(metrics, previous_metrics)
        self.current_block_id += 1
        
        if signal['verdict'] == 'EXECUTE_MARKET_BUY':
            self.execute_buy(metrics['avg_price'], metrics)
        elif signal['verdict'] == 'EXECUTE_MARKET_SELL':
            self.execute_sell(metrics['avg_price'], metrics)
        elif signal['verdict'] == 'EXIT_POSITION' and self.in_position:
            self.execute_exit(metrics['avg_price'], signal['reason'], metrics)
        
        # Save to CSV
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                self.current_block_id,
                self.block_start.strftime('%Y-%m-%d %H:%M:%S'),
                self.block_end.strftime('%Y-%m-%d %H:%M:%S'),
                round(metrics['total_buys'], 6),
                round(metrics['total_sells'], 6),
                round(metrics['total_volume'], 6),
                metrics['buy_count'],
                metrics['sell_count'],
                metrics['total_trades'],
                round(metrics['delta'], 4),
                round(metrics['cumulative_delta'], 4),
                round(metrics['buy_pressure'], 1),
                round(metrics['sell_pressure'], 1),
                round(metrics['vwap'], 2),
                round(metrics['avg_price'], 2),
                round(metrics['min_price'], 2),
                round(metrics['max_price'], 2),
                metrics['poc_price'] or 0,
                round(metrics['poc_volume'], 6) if metrics['poc_volume'] else 0,
                round(metrics['flow_velocity'], 1),
                metrics['large_trades'],
                round(metrics['whale_volume'], 6),
                metrics['iceberg_detected'],
                metrics['absorption'],
                metrics['divergence'],
                metrics['sentiment'],
                signal['state'],
                signal['verdict'],
                signal['confidence'],
                signal['reason'],
                self.in_position,
                round(self.entry_price, 2) if self.in_position else 0,
                round(self.tp1_price, 2) if self.in_position else 0,
                round(self.tp2_price, 2) if self.in_position else 0,
                round(self.sl_price, 2) if self.in_position else 0
            ])
        
        # Print summary
        self.print_summary(metrics, signal)

    def print_summary(self, metrics, signal):
        print("\n" + "="*80)
        print(f"🏦 BLOCK #{self.current_block_id} | {self.block_start.strftime('%H:%M')}→{self.block_end.strftime('%H:%M')}")
        print("="*80)
        print(f"💰 Price: ${metrics['avg_price']:.2f} | Delta: {metrics['delta']:+.2f} | Cum: {metrics['cumulative_delta']:+.2f}")
        print(f"🟢 Buy: {metrics['buy_pressure']:.1f}% | 🔴 Sell: {metrics['sell_pressure']:.1f}%")
        print(f"📊 Volume: {metrics['total_volume']:.2f} BTC | Trades: {metrics['total_trades']}")
        print(f"🎯 Signal: {signal['verdict']} | Confidence: {signal['confidence']}/10")
        if self.in_position:
            print(f"📋 POSITION: Entry ${self.entry_price:.2f} | P&L: {(metrics['avg_price']-self.entry_price)/self.entry_price*100:+.2f}%")
        print("="*80)

    def run(self):
        print("="*80)
        print("🏦 PROFESSIONAL ORDER FLOW SYSTEM")
        print("="*80)
        print(f"💰 Symbol: {self.symbol}")
        print(f"⏰ Block Duration: {config.BLOCK_MINUTES} minutes")
        print("📊 WhatsApp Alerts: ENABLED")
        print(f"📁 Logging: {self.csv_file}")
        print("="*80)
        print("🟢 Running... Press Ctrl+C to stop\n")
        
        current_time = datetime.now()
        self.block_start, self.block_end = self.get_next_block(current_time)
        self.block_trades = []
        previous_metrics = None
        
        print(f"⏳ Current Block: {self.block_start.strftime('%H:%M:%S')} → {self.block_end.strftime('%H:%M:%S')}")
        
        while self.is_running:
            try:
                current_time = datetime.now()
                
                if current_time >= self.block_end:
                    self.process_block(previous_metrics)
                    
                    if self.block_trades:
                        previous_metrics = self.calculate_block_metrics()
                    
                    self.block_start = self.block_end
                    self.block_end = self.block_start + timedelta(minutes=config.BLOCK_MINUTES)
                    self.block_trades = []
                    print(f"\n⏳ New Block: {self.block_start.strftime('%H:%M:%S')} → {self.block_end.strftime('%H:%M:%S')}")
                
                new_trades = self.get_new_trades()
                
                if new_trades:
                    for trade in new_trades:
                        categorized = self.categorize_trade(trade)
                        trade_time = categorized['timestamp']
                        
                        if trade_time >= self.block_start and trade_time < self.block_end:
                            self.block_trades.append(categorized)
                
                time.sleep(0.5)
                
            except KeyboardInterrupt:
                print("\n\n🛑 Stopping...")
                if self.block_trades:
                    print("💾 Saving final block...")
                    self.process_block(previous_metrics)
                if self.in_position:
                    print("🟡 Closing position...")
                    self.execute_exit(self.block_trades[-1]['price'] if self.block_trades else 0, "System Shutdown", {})
                self.is_running = False
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                time.sleep(1)

if __name__ == "__main__":
    system = ProfessionalOrderFlowSystem(config.SYMBOL)
    system.run()