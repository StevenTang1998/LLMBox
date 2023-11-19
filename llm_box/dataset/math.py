from .generation_dataset import GenerationDataset
from datasets import load_dataset, load_from_disk
import numpy as np
import re

SUBSTITUTIONS = [
    ('an ', ''), ('a ', ''), ('.$', '$'), ('\\$', ''), (r'\ ', ''),
    (' ', ''), ('mbox', 'text'), (',\\text{and}', ','),
    ('\\text{and}', ','), ('\\text{m}', '\\text{}')
]
REMOVED_EXPRESSIONS = [
    'square', 'ways', 'integers', 'dollars', 'mph', 'inches', 'ft',
    'hours', 'km', 'units', '\\ldots', 'sue', 'points', 'feet',
    'minutes', 'digits', 'cents', 'degrees', 'cm', 'gm', 'pounds',
    'meters', 'meals', 'edges', 'students', 'childrentickets', 'multiples',
    '\\text{s}', '\\text{.}', '\\text{\ns}', '\\text{}^2',
    '\\text{}^3', '\\text{\n}', '\\text{}', r'\mathrm{th}',
    r'^\circ', r'^{\circ}', r'\;', r',\!', '{,}', '"', '\\dots'
 ]

class Math(GenerationDataset):
    """The dataset of MATH.

    MATH(Hendrycks et al. 2021), a dataset of 12,500 challenging competition mathematics problems  with step-by-step solutions
    written in LATEX and natural language.

    Examples:
        problem: Let \[f(x) = \left\{ \begin{array}{cl} ax+3, &\text{ if }x>2, \\ x-5 &\text{ if } -2 \le x \le 2, \\ 2x-b &\text{ if } x <-2. \end{array} \right.\]Find $a+b$ if the piecewise function is continuous (which means that its graph can be drawn without lifting your pencil from the paper).
        level: Level 5
        type: Algebra
        solution: For the piecewise function to be continuous, the cases must "meet" at $2$ and $-2$. For example, $ax+3$ and $x-5$ must be equal when $x=2$. This implies $a(2)+3=2-5$, which we solve to get $2a=-6 \Rightarrow a=-3$. Similarly, $x-5$ and $2x-b$ must be equal when $x=-2$. Substituting, we get $-2-5=2(-2)-b$, which implies $b=3$. So $a+b=-3+3=\boxed{0}$.
    """

    def __init__(self, args, model):
        self.name = "math"
        dataset = load_dataset("hendrycks/competition_math")
        # dataset = load_from_disk("hendrycks/competition_math")
        self.example_data = list(dataset["train"])
        self.evaluation_data = list(dataset["test"])
        self.instruction = "Answer the following question."

        self.metric = "accuracy"
        super().__init__(args, model)

    def normalize_final_answer(self, final_answer: str) -> str:
        """Normalize a final answer to a quantitative reasoning question."""
        final_answer = final_answer.split('=')[-1]

        for before, after in SUBSTITUTIONS:
            final_answer = final_answer.replace(before, after)
        for expr in REMOVED_EXPRESSIONS:
            final_answer = final_answer.replace(expr, '')

        # Extract answer that is in LaTeX math, is bold,
        # is surrounded by a box, etc.
        final_answer = re.sub(r'(.*?)(\$)(.*?)(\$)(.*)', '$\\3$', final_answer)
        print(final_answer)
        final_answer = re.sub(r'(\\text\{)(.*?)(\})', '\\2', final_answer)
        final_answer = re.sub(r'(\\textbf\{)(.*?)(\})', '\\2', final_answer)
        final_answer = re.sub(r'(\\overline\{)(.*?)(\})', '\\2', final_answer)
        final_answer = re.sub(r'(\\boxed\{)(.*)(\})', '\\2', final_answer)

        # Normalize shorthand TeX:
        # \fracab -> \frac{a}{b}
        # \frac{abc}{bef} -> \frac{abc}{bef}
        # \fracabc -> \frac{a}{b}c
        # \sqrta -> \sqrt{a}
        # \sqrtab -> sqrt{a}b
        final_answer = re.sub(r'(frac)([^{])(.)', 'frac{\\2}{\\3}', final_answer)
        final_answer = re.sub(r'(sqrt)([^{])', 'sqrt{\\2}', final_answer)
        final_answer = final_answer.replace('$', '')

        # Normalize 100,000 -> 100000
        if final_answer.replace(',', '').isdigit():
            final_answer = final_answer.replace(',', '')

        return final_answer

    def extract_inner_content(self, text):
        # extract from \boxed{...}, where{} can be nested
        start = text.find("\\boxed{")
        if start == -1:
            return None
        start += 7
        count = 1
        end = start
        while count > 0 and end < len(text):
            if text[end] == "{":
                count += 1
            elif text[end] == "}":
                count -= 1
            end += 1
        return text[start:end - 1]

    def answer_cleansing(self, preds):
        predictions = []
        pattern = r'\$(.*?)\$'
        for pred in preds:
            if ('The answer is ' in pred):
                pred = pred.split('The answer is ')[-1].strip()
            final_answer = re.findall(pattern, pred)
            if final_answer:
                predictions.append(self.normalize_final_answer(final_answer[-1]))
            else:
                numbers = re.findall(r"[-+]?\d*\.\d+|\d+", pred)
                predictions.append(numbers[-1] if numbers else pred)

        return predictions

    def format_instance(self, instance):
        ans = self.extract_inner_content(instance["solution"])
        instance["problem"] = "Q: " + instance["problem"] + "\n" + "A:"
        instance["solution"] = " " + instance["solution"] + f"\nThe answer is ${ans}$"
        return dict(
            source=instance["problem"],
            target=instance["solution"],
        )

    def calculate_metric(self, predictions):
        predictions = self.answer_cleansing(predictions)
        score_list = np.asarray(predictions) == np.asarray(self.references)
        return {'Accuracy': np.mean(score_list)}

    @property
    def references(self):
        return [self.extract_inner_content(instance["solution"]) for instance in self.evaluation_data]