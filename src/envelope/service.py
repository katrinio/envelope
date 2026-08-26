FINANCIAL_PILLOW_SALARY_MULTIPLIER = 2


def calculate_financial_pillow_target(monthly_salary: int) -> int:
    if monthly_salary <= 0:
        raise ValueError("A positive salary is needed for a financial pillow.")
    return monthly_salary * FINANCIAL_PILLOW_SALARY_MULTIPLIER
