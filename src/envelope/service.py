FINANCIAL_PILLOW_SALARY_MULTIPLIER = 2


def calculate_financial_pillow_target(
    monthly_salary: int,
    pillow_index: int = FINANCIAL_PILLOW_SALARY_MULTIPLIER,
) -> int:
    if monthly_salary <= 0:
        raise ValueError("A positive salary is needed for a financial pillow.")
    if pillow_index <= 0:
        raise ValueError("A positive pillow index is required.")
    return monthly_salary * pillow_index
