# strategy.py

from decimal import Decimal
from typing import Optional, Dict
from .models import BotConfig, Trade, GridLevelState
from .exchange import ExchangeInterface
import json

class GridStrategy:
    """
    Implements the "Single-Runner Relay Grid" strategy for perpetual contracts
    using a state machine approach.
    """

    def __init__(self, config: BotConfig, exchange: ExchangeInterface):
        self.config = config
        self.exchange = exchange
        self.grid_levels: Dict[Decimal, GridLevelState] = {}
        self.state_file_path = f"grid_state_{self.config.name.replace('/', '_')}.json"
        
        # Derived from config for quick access
        self.side = self.config.strategy_side
        self.grid_step = self.config.grid_step
        self.upper_price = self.config.upper_price
        self.lower_price = self.config.lower_price

    async def initialize_grid(self, fresh_start: bool = False):
        """Initializes the grid, cleans up old state, and places initial orders."""
        if fresh_start:
            print("Fresh start requested. Cleaning up all existing positions and orders...")
            await self._cleanup_exchange_state()
            self.grid_levels = {}
        else:
            await self._load_state()

        if not self.grid_levels:
            self._create_grid_levels()
        else:
            # 检查已加载状态中的订单实际状态
            await self._sync_order_states()

        await self._place_initial_orders()
        await self._save_state()
        print("Grid strategy initialized successfully.")

    def _create_grid_levels(self):
        """Creates the initial state for all grid price levels."""
        print("Creating new grid levels...")
        for i in range(self.config.grids):
            price = self.lower_price + i * self.grid_step
            # On the upper boundary, we don't place an open order for long side
            if self.side == "long" and price == self.upper_price:
                continue
            # On the lower boundary, we don't place an open order for short side
            if self.side == "short" and price == self.lower_price:
                continue
            
            self.grid_levels[price] = GridLevelState(price=price, status="AVAILABLE")

    async def _sync_order_states(self):
        """Syncs local state with the exchange upon restart."""
        print("Syncing order states with exchange...")
        open_orders = await self.exchange.fetch_open_orders()
        open_order_ids = {o['id'] for o in open_orders}

        for price, level in self.grid_levels.items():
            # Case 1: We think an open order is pending
            if level.status == "ORDER_PENDING" and level.open_order_id:
                if level.open_order_id not in open_order_ids:
                    # The order is not open anymore, check if it was filled or cancelled
                    try:
                        order = await self.exchange.fetch_order(level.open_order_id)
                        if order['status'] == 'closed':
                            print(f"Sync: Found filled OPEN order {level.open_order_id} at {price}.")
                            # Create a Trade object from the order
                            trade = Trade(
                                order_id=order['id'],
                                side=order['side'],
                                amount=order['amount'],
                                price=Decimal(str(order['price']))
                            )
                            await self._handle_open_order_fill(level, trade)
                        else: # cancelled or other states
                            print(f"Found canceled order {level.open_order_id} at price {price}")
                            level.status = "AVAILABLE"
                            level.open_order_id = None
                    except Exception as e:
                        print(f"Error fetching order {level.open_order_id}: {e}")
                        level.status = "AVAILABLE" # Can't fetch, assume it's gone
                        level.open_order_id = None

            # Case 2: We think we are holding a position
            elif level.status == "POSITION_HELD":
                if level.close_order_id and level.close_order_id not in open_order_ids:
                    # The close order is gone, check its status
                    try:
                        order = await self.exchange.fetch_order(level.close_order_id)
                        if order['status'] == 'closed':
                            print(f"Sync: Found filled CLOSE order {level.close_order_id} for position at {price}.")
                            trade = Trade(
                                order_id=order['id'],
                                side=order['side'],
                                amount=order['amount'],
                                price=Decimal(str(order['price']))
                            )
                            await self._handle_close_order_fill(level, trade)
                        else: # Close order was cancelled, we need to replace it
                            print(f"Sync: Close order for {price} was cancelled. Re-placing.")
                            await self._place_close_order_from_sync(level)
                    except Exception as e:
                        print(f"Error fetching close order {level.close_order_id}: {e}")
                        # Can't fetch, assume it was cancelled and replace it
                        await self._place_close_order_from_sync(level)
                elif not level.close_order_id:
                    # We hold a position but have no record of a close order. This is a zombie position.
                    print(f"Sync: Found a zombie position at {price} without a close order. Placing one now.")
                    await self._place_close_order_from_sync(level)

    async def _place_close_order_from_sync(self, level: GridLevelState):
        """Helper method for placing close orders for existing positions during sync"""
        if not level.position_amount:
            print(f"Error: Cannot place close order for {level.price}, position amount is unknown.")
            return # Or fetch position size from exchange

        close_price = level.price + self.grid_step if self.side == "long" else level.price - self.grid_step
        params = {'positionSide': 'LONG' if self.side == 'long' else 'SHORT'}

        try:
            if self.side == "long":
                # 平多仓：卖出
                order = await self.exchange.create_limit_sell_order(level.position_amount, close_price, params)
            else:
                # 平空仓：买入
                order = await self.exchange.create_limit_buy_order(level.position_amount, close_price, params)

            level.close_order_id = order['id']
            print(f"Sync: Placed close order {order['id']} for position at {level.price}, target price {close_price}")
        except Exception as e:
            print(f"Error placing close order from sync for position at {level.price}: {e}")

    async def _place_close_order(self, level, filled_order):
        """为已成交的订单放置平仓单"""
        try:
            close_price = level.price + self.grid_step if self.side == "long" else level.price - self.grid_step
            # 双向持仓模式：平仓通过positionSide和相反的side实现
            params = {
                'positionSide': 'LONG' if self.side == 'long' else 'SHORT'
            }

            # 平仓逻辑：
            # 平多仓：positionSide=LONG, side=SELL
            # 平空仓：positionSide=SHORT, side=BUY
            if self.side == "long":
                # 平多仓：卖出
                order = await self.exchange.create_limit_sell_order(level.position_amount, close_price, params)
            else:
                # 平空仓：买入
                order = await self.exchange.create_limit_buy_order(level.position_amount, close_price, params)

            level.close_order_id = order['id']
            print(f"Placed CLOSE order {order['id']} for position at {level.price}, target price {close_price}")
        except Exception as e:
            print(f"Error placing close order for position at {level.price}: {e}")

    async def _place_initial_orders(self):
        """Places 'open' orders for all grid levels in 'AVAILABLE' state."""
        print("Placing initial orders...")

        # 获取当前市场价格
        ticker = await self.exchange.fetch_ticker()
        current_price = Decimal(str(ticker['last']))
        print(f"Current market price: {current_price}")

        for price, level in self.grid_levels.items():
            if level.status == "AVAILABLE":
                try:
                    order_amount_coin = self.config.order_amount_usdt / price

                    # --- KEY CHANGE HERE ---
                    params = {
                        'positionSide': 'LONG' if self.side == 'long' else 'SHORT',
                        'postOnly': True  # Ensure it's a MAKER order
                    }

                    # 做多策略：在所有网格价格都放置买入挂单
                    if self.side == "long":
                        # 跳过与当前价格太接近的层级，避免立即成交
                        price_diff = abs(price - current_price) / current_price
                        if price_diff < Decimal('0.001'):  # 0.1%以内跳过
                            print(f"Skipping order at {price} (too close to current price {current_price})")
                            continue

                        # 在所有其他价格放置买入挂单
                        order = await self.exchange.create_limit_buy_order(order_amount_coin, price, params)
                        level.open_order_id = order['id']
                        level.status = "ORDER_PENDING"
                        position = "below" if price < current_price else "above"
                        print(f"Placed BUY order {order['id']} at {price} ({position} current price)")

                    else: # short strategy
                        # 做空策略：在所有网格价格都放置卖出挂单
                        price_diff = abs(price - current_price) / current_price
                        if price_diff < Decimal('0.001'):  # 0.1%以内跳过
                            print(f"Skipping order at {price} (too close to current price {current_price})")
                            continue

                        order = await self.exchange.create_limit_sell_order(order_amount_coin, price, params)
                        level.open_order_id = order['id']
                        level.status = "ORDER_PENDING"
                        position = "below" if price < current_price else "above"
                        print(f"Placed SELL order {order['id']} at {price} ({position} current price)")

                except Exception as e:
                    # postOnly订单如果会立即成交，会抛出 OrderImmediatelyFillable 或 Cancelled 错误，这是正常的
                    if ('postonly' in str(e).lower() or 'immediately' in str(e).lower() or
                        'would immediately match' in str(e).lower() or 'post only order will be rejected' in str(e).lower() or
                        'could not be executed as maker' in str(e).lower()):
                        print(f"Skipping order at {price}: It would fill immediately (expected for prices above current market).")
                    elif 'limit price can\'t be higher' in str(e).lower() or 'limit price can\'t be lower' in str(e).lower():
                        print(f"Skipping order at {price}: Price outside exchange limits.")
                    else:
                        print(f"Error placing initial order at {price}: {e}")

    async def handle_filled_order(self, trade: Trade):
        """The core state machine logic for handling filled orders."""
        print(f"--- Handling Filled Order: ID {trade.order_id}, Side {trade.side}, Price {trade.price} ---")

        filled_level_price = None
        # First try to find by order ID
        for price, level in self.grid_levels.items():
            if level.open_order_id == trade.order_id:
                await self._handle_open_order_fill(level, trade)
                filled_level_price = price
                break
            elif level.close_order_id == trade.order_id:
                await self._handle_close_order_fill(level, trade)
                filled_level_price = price
                break

        # If not found by order ID, try to find by price (with tolerance)
        if filled_level_price is None:
            print(f"Order ID {trade.order_id} not found, trying to match by price {trade.price}")
            tolerance = Decimal('0.0001')  # 0.01% tolerance
            for price, level in self.grid_levels.items():
                price_diff = abs(price - trade.price) / price
                if price_diff <= tolerance and level.status == "ORDER_PENDING":
                    print(f"Found matching grid level by price: {price} (diff: {price_diff:.6f})")
                    # Update the order ID and handle the fill
                    level.open_order_id = trade.order_id
                    await self._handle_open_order_fill(level, trade)
                    filled_level_price = price
                    break

        if filled_level_price is None:
            print(f"Warning: Filled order {trade.order_id} at price {trade.price} does not match any known grid level. Ignoring.")
            return

        await self._save_state()
        print("--- Finished Handling Order ---")

    async def _handle_open_order_fill(self, level: GridLevelState, trade: Trade):
        """Logic for when an 'open' order is filled."""
        print(f"OPEN order filled at price {level.price}. Transitioning to POSITION_HELD.")
        
        # 1. Update state
        level.status = "POSITION_HELD"
        level.open_order_id = None
        level.position_amount = trade.amount

        # 2. Check risk management
        current_positions = sum(1 for lvl in self.grid_levels.values() if lvl.status == 'POSITION_HELD')
        if current_positions > self.config.max_position_count:
            print(f"CRITICAL: Position count ({current_positions}) exceeds max limit ({self.config.max_position_count}).")
            # Here you could trigger a bot shutdown or other emergency action.
            # For now, we just print a warning.

        # 3. Place the corresponding 'close' order
        try:
            close_price = level.price + self.grid_step if self.side == "long" else level.price - self.grid_step
            # 双向持仓模式：平仓通过positionSide和相反的side实现
            params = {
                'positionSide': 'LONG' if self.side == 'long' else 'SHORT'
            }

            # 平仓逻辑：
            # 平多仓：positionSide=LONG, side=SELL
            # 平空仓：positionSide=SHORT, side=BUY
            if self.side == "long":
                # 平多仓：卖出
                order = await self.exchange.create_limit_sell_order(trade.amount, close_price, params)
            else: # short
                # 平空仓：买入
                order = await self.exchange.create_limit_buy_order(trade.amount, close_price, params)
                
            level.close_order_id = order['id']
            print(f"Placed CLOSE order {order['id']} for position at {level.price}, target price {close_price}")

        except Exception as e:
            print(f"Error placing CLOSE order for position at {level.price}: {e}")
            # In a real scenario, you'd need a retry mechanism or alert.

    async def _handle_close_order_fill(self, level: GridLevelState, trade: Trade):
        """Logic for when a 'close' order is filled, completing the cycle."""
        print(f"CLOSE order filled for position at {level.price}. Cycle complete. Re-placing OPEN order.")

        # 1. Update state back to available
        level.status = "AVAILABLE"
        level.close_order_id = None
        level.position_amount = None

        # 2. Re-place the 'open' order to restart the cycle for this level
        try:
            order_amount_coin = self.config.order_amount_usdt / level.price

            # --- KEY CHANGE HERE ---
            params = {
                'positionSide': 'LONG' if self.side == 'long' else 'SHORT',
                'postOnly': True # Also for re-placing orders
            }

            if self.side == "long":
                order = await self.exchange.create_limit_buy_order(order_amount_coin, level.price, params)
            else: # short
                order = await self.exchange.create_limit_sell_order(order_amount_coin, level.price, params)

            level.open_order_id = order['id']
            level.status = "ORDER_PENDING"
            print(f"Re-placed OPEN order {order['id']} at {level.price}")
        except Exception as e:
            # postOnly订单如果会立即成交，会抛出异常，这是正常的
            if 'postonly' in str(e).lower() or 'immediately' in str(e).lower() or 'would immediately match' in str(e).lower():
                print(f"Skipping re-placing order at {level.price}: It would fill immediately.")
            else:
                print(f"Error re-placing OPEN order at {level.price}: {e}")

    async def _cleanup_exchange_state(self):
        """Closes all positions and cancels all orders for the pair."""
        try:
            # This is a simplified cleanup. A robust version would fetch positions first.
            # For now, we assume we need to close a position if we have one.
            # A better implementation would be in exchange.py
            print("Closing any open positions...")
            # This logic needs to be robust, check current position side and size
            # For now, let's just try to close both ways if needed, or implement in exchange.py
            
            print("Cancelling all open orders...")
            open_orders = await self.exchange.fetch_open_orders()
            for order in open_orders:
                await self.exchange.cancel_order(order['id'])
            print(f"Cancelled {len(open_orders)} orders.")
        except Exception as e:
            print(f"Error during cleanup: {e}")

    async def check_order_health(self):
        """Periodically syncs our state with the exchange."""
        # This is a complex but crucial method for a robust bot.
        # It should:
        # 1. Fetch all open orders from the exchange.
        # 2. Compare them with our `self.grid_levels` state.
        # 3. If an order in our state is not on the exchange, check its status (filled? cancelled?).
        # 4. If an order on the exchange is not in our state, something is wrong (cancel it?).
        # For this first refactoring step, we'll leave it as a placeholder.
        pass

    async def _save_state(self):
        """Saves the current grid state to a file."""
        try:
            # Pydantic's built-in json() method handles Decimal serialization correctly
            state_to_save = {str(k): json.loads(v.json()) for k, v in self.grid_levels.items()}
            with open(self.state_file_path, 'w') as f:
                json.dump(state_to_save, f, indent=4)
        except Exception as e:
            print(f"Error saving state: {e}")

    async def _load_state(self):
        """Loads grid state from a file."""
        try:
            with open(self.state_file_path, 'r') as f:
                loaded_state = json.load(f)
                self.grid_levels = {
                    Decimal(k): GridLevelState(**v) for k, v in loaded_state.items()
                }
                print(f"Successfully loaded state for {len(self.grid_levels)} grid levels.")
        except FileNotFoundError:
            print("No state file found. Starting fresh.")
            self.grid_levels = {}
        except Exception as e:
            print(f"Error loading state: {e}")
            self.grid_levels = {}