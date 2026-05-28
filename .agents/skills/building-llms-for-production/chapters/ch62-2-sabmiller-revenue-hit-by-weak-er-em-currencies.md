# Chapter 62: SABMiller Revenue Hit by Weak EM Currencies

## Core Idea
SABMiller's revenue decline was attributed to weakening Emerging Market (EM) currencies, which negatively impacted consumer spending on premium products like whiskey.

## Frameworks Introduced
- **Value at Risk (VaR)**: A statistical model used to estimate potential losses from extreme market movements.  
  - When to use: To assess the risk of significant financial loss due to currency fluctuations.
  - How: Calculates maximum potential loss over a specific time frame with high confidence.

## Key Concepts
- **Value at Risk (VaR)**: Measures the worst-case scenario for portfolio losses, expressed as a percentage or absolute figure.
- **Stress Testing**: Evaluates a company's financial resilience under extreme but plausible scenarios.

## Mental Models
- Use VaR when analyzing currency fluctuations' impact on revenue. For example, "Analyze potential losses using VaR to understand EM currency risks."

## Anti-patterns
- Overreliance on historical data: Ignoring current market conditions like inflation rates can lead to inaccurate risk assessments and poor decision-making.

## Code Examples
```r
# Example R script for VaR calculation
VaR <- function(returns, confidence = 0.95, holding_period = 252) {
    if (confidence > 1 || confidence < 0) {
        stop("Confidence level must be between 0 and 1")
    }
    if (holding_period <= 0 || !is.numeric(holding_period)) {
        stop("Invalid holding period")
    }
    
    # Calculate historical returns
    mu <- mean(returns)
    sigma <- sd(returns)
    
    # Annualized parameters
    n = length(returns)
    log_returns = log(1 + returns)
    mu_annual = (exp(mu) - 1) * sqrt(252)
    sigma_annual = sigma * sqrt(252)
    
    # VaR calculation for one day
    var_one_day <- mu + qnorm(confidence) * sigma
    
    # VaR for holding period
    varholding <- mu * holding_period + qnorm(confidence) * sigma * sqrt(holding_period)
    
    return(c(VaR_one_day = exp(var_one_day), 
             VaR_holding = exp(varholding)))
}

# Example stress testing metric calculation
stress_test <- function(data, scenarios) {
  # Simulate extreme market conditions
  stressed_data <- data * scenarios
  
  # Calculate key metrics under stress
  list(
    revenue = sum(stressed_data),
    profits = mean(stressed_data),
    currency_stress = max(stressed_data)
  )
}
```

## Reference Tables
| Parameter          | Description                                                                 |
|--------------------|-----------------------------------------------------------------------------|
| VaR Confidence     | Probability level indicating the certainty of the loss estimate.         |
| VaR Holding Period  | Time frame for assessing potential losses (e.g., 1 day, 1 month).        |
| Stress Scenario    | Extreme but plausible market conditions to test financial resilience.      |

## Key Takeaways
1. Accurate forecasting is crucial for identifying currency-related risks.
2. Robust risk management frameworks like VaR and stress testing are essential for mitigating financial losses.
3. Continuous monitoring of macroeconomic factors, such as inflation rates, improves decision-making.

## Connects To
- Risk Management chapter on VaR and stress testing
- Financial Analysis techniques for identifying market impacts