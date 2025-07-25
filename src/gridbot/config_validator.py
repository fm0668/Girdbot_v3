"""
配置验证器 - 验证配置合理性并提供优化建议
"""

from decimal import Decimal
from typing import List, Dict, Tuple
from .models import DualAccountConfig

class ConfigValidator:
    """配置验证器"""
    
    def __init__(self, config: DualAccountConfig):
        self.config = config
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.suggestions: List[str] = []
    
    def validate_all(self) -> Tuple[bool, Dict]:
        """执行全面验证"""
        self.warnings.clear()
        self.errors.clear()
        self.suggestions.clear()
        
        # 基础配置验证
        self._validate_basic_config()
        
        # 价格区间验证
        self._validate_price_range()
        
        # 网格配置验证
        self._validate_grid_config()
        
        # 风险管理验证
        self._validate_risk_management()
        
        # 对冲特定验证
        self._validate_hedge_config()
        
        # 性能优化建议
        self._generate_optimization_suggestions()
        
        is_valid = len(self.errors) == 0
        
        return is_valid, {
            'errors': self.errors,
            'warnings': self.warnings,
            'suggestions': self.suggestions
        }
    
    def _validate_basic_config(self):
        """验证基础配置"""
        # 检查API密钥
        if not self.config.long_api_key or not self.config.long_api_secret:
            self.errors.append("多头账户API密钥不能为空")
        
        if not self.config.short_api_key or not self.config.short_api_secret:
            self.errors.append("空头账户API密钥不能为空")
        
        # 检查API密钥是否相同
        if (self.config.long_api_key == self.config.short_api_key and 
            self.config.long_api_secret == self.config.short_api_secret):
            self.errors.append("多头和空头账户不能使用相同的API密钥")
        
        # 检查杠杆设置
        if self.config.leverage > 20:
            self.warnings.append(f"杠杆倍数 {self.config.leverage}x 较高，建议谨慎使用")
        
        if self.config.leverage < 5:
            self.suggestions.append("杠杆倍数较低，可能影响资金效率")
    
    def _validate_price_range(self):
        """验证价格区间"""
        price_range = self.config.upper_price - self.config.lower_price
        price_center = (self.config.upper_price + self.config.lower_price) / 2
        
        # 检查价格区间合理性
        range_percentage = (price_range / price_center) * 100
        
        if range_percentage < 5:
            self.warnings.append(f"价格区间过窄 ({range_percentage:.1f}%)，可能限制盈利机会")
        elif range_percentage > 50:
            self.warnings.append(f"价格区间过宽 ({range_percentage:.1f}%)，可能增加风险")
        
        # 检查网格密度
        grid_density = price_range / self.config.grids
        if grid_density < price_center * Decimal('0.001'):  # 0.1%
            self.warnings.append("网格过于密集，可能导致频繁交易")
        elif grid_density > price_center * Decimal('0.05'):  # 5%
            self.warnings.append("网格过于稀疏，可能错过盈利机会")
    
    def _validate_grid_config(self):
        """验证网格配置"""
        # 检查网格数量
        if self.config.grids < 5:
            self.warnings.append("网格数量过少，建议至少5个网格")
        elif self.config.grids > 50:
            self.warnings.append("网格数量过多，可能影响管理效率")
        
        # 检查单网格金额
        if self.config.order_amount_usdt < 10:
            self.warnings.append("单网格金额过小，可能不符合交易所最小订单要求")
        elif self.config.order_amount_usdt > 10000:
            self.warnings.append("单网格金额较大，建议评估风险承受能力")
        
        # 计算总投资金额
        max_investment = self.config.order_amount_usdt * self.config.max_position_count * 2  # 双账户
        if max_investment > 100000:
            self.warnings.append(f"最大投资金额 {max_investment} USDT 较大，请确保资金充足")

    def _validate_risk_management(self):
        """验证风险管理"""
        # 检查最大持仓数量
        max_position_ratio = self.config.max_position_count / self.config.grids

        if max_position_ratio > 0.8:
            self.warnings.append("最大持仓比例过高，建议降低以控制风险")
        elif max_position_ratio < 0.3:
            self.suggestions.append("最大持仓比例较低，可能限制盈利潜力")

        # 检查对冲不平衡容忍度
        if self.config.max_imbalance_ratio > Decimal('0.2'):
            self.warnings.append("对冲不平衡容忍度过高，可能影响对冲效果")
        elif self.config.max_imbalance_ratio < Decimal('0.05'):
            self.warnings.append("对冲不平衡容忍度过低，可能导致频繁调整")

    def _validate_hedge_config(self):
        """验证对冲特定配置"""
        # 检查同步容忍时间
        if self.config.sync_tolerance_seconds > 120:
            self.warnings.append("同步容忍时间过长，可能影响对冲效果")
        elif self.config.sync_tolerance_seconds < 10:
            self.warnings.append("同步容忍时间过短，可能导致误报")

        # 检查沙盒模式
        if not self.config.sandbox_mode:
            self.warnings.append("当前为实盘模式，请确保已充分测试")
        else:
            self.suggestions.append("当前为沙盒模式，测试完成后可切换到实盘")

    def _generate_optimization_suggestions(self):
        """生成优化建议"""
        # 基于配置参数生成优化建议

        # 网格优化建议
        optimal_grids = max(10, min(20, int((self.config.upper_price - self.config.lower_price) / (self.config.upper_price * Decimal('0.01')))))
        if abs(self.config.grids - optimal_grids) > 3:
            self.suggestions.append(f"建议网格数量: {optimal_grids} (当前: {self.config.grids})")

        # 杠杆优化建议
        if self.config.leverage != 10:
            self.suggestions.append("建议杠杆倍数: 10x (平衡风险和收益)")

        # 资金分配建议
        total_grids = self.config.grids - 1  # 排除边界
        recommended_amount = max(50, min(500, 5000 / total_grids))
        if abs(float(self.config.order_amount_usdt) - recommended_amount) > recommended_amount * 0.3:
            self.suggestions.append(f"建议单网格金额: {recommended_amount:.0f} USDT (当前: {self.config.order_amount_usdt})")

    def print_validation_results(self):
        """打印验证结果"""
        print("\n🔍 === 配置验证结果 ===")

        if self.errors:
            print("❌ 错误:")
            for error in self.errors:
                print(f"   {error}")

        if self.warnings:
            print("⚠️ 警告:")
            for warning in self.warnings:
                print(f"   {warning}")

        if self.suggestions:
            print("💡 建议:")
            for suggestion in self.suggestions:
                print(f"   {suggestion}")

        if not self.errors and not self.warnings:
            print("✅ 配置验证通过，无问题发现")

        print("=====================\n")
