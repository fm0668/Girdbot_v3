"""
性能监控器 - 监控系统性能和交易效率
"""

import asyncio
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque

@dataclass
class PerformanceMetrics:
    """性能指标数据结构"""
    timestamp: float
    order_latency: float  # 订单延迟(毫秒)
    sync_delay: float     # 同步延迟(毫秒)
    hedge_effectiveness: float  # 对冲有效性(0-1)
    memory_usage: float   # 内存使用(MB)
    cpu_usage: float      # CPU使用率(%)
    active_connections: int  # 活跃连接数

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.metrics_history: deque = deque(maxlen=window_size)
        self.order_times: Dict[str, float] = {}  # 订单ID -> 提交时间
        self.sync_times: Dict[str, float] = {}   # 配对ID -> 同步时间
        
        # 统计计数器
        self.total_orders = 0
        self.successful_orders = 0
        self.failed_orders = 0
        self.total_syncs = 0
        self.successful_syncs = 0
        
        # 性能阈值
        self.max_order_latency = 5000  # 5秒
        self.max_sync_delay = 10000    # 10秒
        self.min_hedge_effectiveness = 0.8  # 80%
    
    def record_order_submitted(self, order_id: str):
        """记录订单提交时间"""
        self.order_times[order_id] = time.time() * 1000
        self.total_orders += 1
    
    def record_order_filled(self, order_id: str):
        """记录订单成交，计算延迟"""
        if order_id in self.order_times:
            submit_time = self.order_times.pop(order_id)
            latency = time.time() * 1000 - submit_time
            
            if latency <= self.max_order_latency:
                self.successful_orders += 1
            else:
                self.failed_orders += 1
                print(f"⚠️ 订单延迟过高: {order_id}, 延迟 {latency:.1f}ms")
            
            return latency
        return 0
    
    def record_sync_started(self, pair_id: str):
        """记录同步开始时间"""
        self.sync_times[pair_id] = time.time() * 1000
        self.total_syncs += 1
    
    def record_sync_completed(self, pair_id: str):
        """记录同步完成，计算延迟"""
        if pair_id in self.sync_times:
            start_time = self.sync_times.pop(pair_id)
            delay = time.time() * 1000 - start_time
            
            if delay <= self.max_sync_delay:
                self.successful_syncs += 1
            else:
                print(f"⚠️ 同步延迟过高: {pair_id}, 延迟 {delay:.1f}ms")
            
            return delay
        return 0

    async def collect_system_metrics(self) -> PerformanceMetrics:
        """收集系统性能指标"""
        try:
            import psutil

            # 获取当前进程
            process = psutil.Process()

            # 计算平均延迟
            recent_metrics = list(self.metrics_history)[-100:]  # 最近100个样本
            avg_order_latency = sum(m.order_latency for m in recent_metrics) / len(recent_metrics) if recent_metrics else 0
            avg_sync_delay = sum(m.sync_delay for m in recent_metrics) / len(recent_metrics) if recent_metrics else 0

            # 计算对冲有效性
            hedge_effectiveness = self.successful_syncs / self.total_syncs if self.total_syncs > 0 else 1.0

            metrics = PerformanceMetrics(
                timestamp=time.time(),
                order_latency=avg_order_latency,
                sync_delay=avg_sync_delay,
                hedge_effectiveness=hedge_effectiveness,
                memory_usage=process.memory_info().rss / 1024 / 1024,  # MB
                cpu_usage=process.cpu_percent(),
                active_connections=len(process.connections())
            )

            self.metrics_history.append(metrics)
            return metrics

        except ImportError:
            # 如果没有psutil，返回基础指标
            return PerformanceMetrics(
                timestamp=time.time(),
                order_latency=0,
                sync_delay=0,
                hedge_effectiveness=1.0,
                memory_usage=0,
                cpu_usage=0,
                active_connections=0
            )

    def get_performance_summary(self) -> Dict:
        """获取性能摘要"""
        if not self.metrics_history:
            return {
                'total_orders': self.total_orders,
                'successful_orders': self.successful_orders,
                'failed_orders': self.failed_orders,
                'order_success_rate': self.successful_orders / self.total_orders if self.total_orders > 0 else 0,
                'total_syncs': self.total_syncs,
                'successful_syncs': self.successful_syncs,
                'sync_success_rate': self.successful_syncs / self.total_syncs if self.total_syncs > 0 else 0,
                'avg_order_latency': 0,
                'avg_sync_delay': 0,
                'avg_hedge_effectiveness': 1.0,
                'avg_memory_usage': 0,
                'avg_cpu_usage': 0,
            }

        recent_metrics = list(self.metrics_history)[-100:]

        return {
            'total_orders': self.total_orders,
            'successful_orders': self.successful_orders,
            'failed_orders': self.failed_orders,
            'order_success_rate': self.successful_orders / self.total_orders if self.total_orders > 0 else 0,

            'total_syncs': self.total_syncs,
            'successful_syncs': self.successful_syncs,
            'sync_success_rate': self.successful_syncs / self.total_syncs if self.total_syncs > 0 else 0,

            'avg_order_latency': sum(m.order_latency for m in recent_metrics) / len(recent_metrics),
            'avg_sync_delay': sum(m.sync_delay for m in recent_metrics) / len(recent_metrics),
            'avg_hedge_effectiveness': sum(m.hedge_effectiveness for m in recent_metrics) / len(recent_metrics),
            'avg_memory_usage': sum(m.memory_usage for m in recent_metrics) / len(recent_metrics),
            'avg_cpu_usage': sum(m.cpu_usage for m in recent_metrics) / len(recent_metrics),
        }

    def check_performance_alerts(self) -> List[str]:
        """检查性能告警"""
        alerts = []

        if not self.metrics_history:
            return alerts

        latest = self.metrics_history[-1]

        # 检查订单延迟
        if latest.order_latency > self.max_order_latency:
            alerts.append(f"订单延迟过高: {latest.order_latency:.1f}ms")

        # 检查同步延迟
        if latest.sync_delay > self.max_sync_delay:
            alerts.append(f"同步延迟过高: {latest.sync_delay:.1f}ms")

        # 检查对冲有效性
        if latest.hedge_effectiveness < self.min_hedge_effectiveness:
            alerts.append(f"对冲有效性低: {latest.hedge_effectiveness:.2%}")

        # 检查内存使用
        if latest.memory_usage > 500:  # 500MB
            alerts.append(f"内存使用过高: {latest.memory_usage:.1f}MB")

        # 检查CPU使用
        if latest.cpu_usage > 80:  # 80%
            alerts.append(f"CPU使用过高: {latest.cpu_usage:.1f}%")

        return alerts
