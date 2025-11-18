from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0
code = detect(input() or "")
print(code)