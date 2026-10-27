# Chapter 4: 3. Hypothesis Testing

## Core Idea
This chapter teaches how to formulate and test hypotheses using statistical methods, focusing on t-tests and chi-squared tests with Python's scipy.stats library for data-driven insights.

## Frameworks Introduced
- **Hypothesis Testing**: Formulate null (H₀) and alternative (H₁) hypotheses, select appropriate statistical tests based on data type, execute tests to determine significance.
  - When to use: When comparing means or distributions between groups.
  - How: Use t-tests for continuous variables and chi-squared tests for categorical variables.

## Key Concepts
- **t-test**: Measures differences in means between two groups; assumes normal distribution. Used when comparing means of two datasets (e.g., ratings before and after a change).
- **chi-squared test**: Assesses independence between categorical variables; calculates observed vs expected frequencies.
- **Feature Engineering**: Enhances datasets by creating new features from existing data to capture hidden patterns or relationships.
- **Model Selection**: Choosing appropriate machine learning models based on problem type (classification/regression) and dataset characteristics.
- **Training/Testing**: Splitting data into training and testing sets to build and evaluate models, ensuring generalizability.

## Mental Models
- Use a t-test when comparing means between two groups with continuous data. For example, test if a new feature improves ratings by comparing before-and-after scores.
- Think of chi-squared tests as assessing whether categorical variables are independent; use it for analyzing genre distributions across countries in the Netflix dataset.

## Anti-patterns
- **Avoid using t-tests on non-normal data**: This can lead to incorrect conclusions about group differences.

## Code Examples
```python
from scipy.stats import ttest_ind

# Example: Perform a t-test between two groups
group1 = [3.5, 4.0, 2.8, 5.2]
group2 = [2.9, 3.7, 4.6, 4.1]

t_statistic, p_value = ttest_ind(group1, group2)
print(f"T-statistic: {t_statistic:.3f}, P-value: {p_value:.3f}")
```
- **What it demonstrates**: Conducting a two-sample t-test to compare means of independent groups.

## Reference Tables
| Data Type       | Appropriate Test          |
|-----------------|----------------------------|
| Continuous      | T-test                     |
| Categorical    | Chi-squared test           |

## Key Takeaways
1. Formulate clear hypotheses before testing.
2. Choose the right statistical test based on data type and distribution.
3. Use hypothesis testing to validate insights from exploratory data analysis.

## Connects To
- Relates to Exploratory Data Analysis (EDA) for initial insights.
- Links to Model Evaluation Metrics for assessing predictive models' performance.