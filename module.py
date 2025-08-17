# 共通
def fibonacci_sequence(n):
    if n < 1:
        return []
    seq = [1, 1]
    while len(seq) < n+1:
        seq.append(seq[-1] + seq[-2])
    # 先頭の1を除外
    return seq[1:n+1]

def fibonacci_ratios(count, reverse=False, blend=1.0):
    fibs = fibonacci_sequence(count)
    base = [1] * count
    weights = [(1-blend)*b + blend*f for b, f in zip(base, fibs)]
    total = sum(weights)
    ratios = []
    cum = 0.0
    for w in weights:
        cum += w
        ratios.append(cum/total)
    # 端点（0, 1）は含めない
    ratios = ratios[:-1]
    ratios = list(reversed(ratios))
    if reverse:
        ratios = list(reversed(ratios))
    return ratios
