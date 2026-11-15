"""fonts/ の読書 UD を元の BIZ UD・BIZ UDP と突き合わせる検査。対象ごとのモジュールに分けてある。

検査 (step) は関数で、引数が無いものはフォントに依らない検査、`FontContext` を取るものは
書体 × 太さごとの検査。どの順に実行するかは `scripts/check.py` が持つ。モジュールの名前が、
`check.py --only` で選ぶ検査の名前になる。
"""
