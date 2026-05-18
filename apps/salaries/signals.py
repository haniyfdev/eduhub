# Salary expense mirroring is handled by the pay/mark-paid actions,
# not by post_save signals. Expenses are created when money actually moves,
# not when a salary record is first calculated.
