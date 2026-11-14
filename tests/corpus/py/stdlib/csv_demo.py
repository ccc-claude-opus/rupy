import csv
import io
import os

lines = ['name,age,city\n', 'Ann,31,"New York, NY"\n', '"Bob ""B"" Smith",42,Paris\n', '\n', 'Cy,,"multi\n', 'line"\n', 'last,row']
for row in csv.reader(lines):
    print(row)
print(list(csv.reader(["a;b;'c;d'", " x; y"], delimiter=";", quotechar="'", skipinitialspace=True)))
print(list(csv.reader(["a\\,b,c"], escapechar="\\")), list(csv.reader(['"unterminated'])), list(csv.reader(['x,"a"b,c'])))
r = csv.reader(["h1,h2", "1,2", "3,4"])
header = next(r)
print(header, [row for row in r])

buf = io.StringIO()
w = csv.writer(buf)
print(w.writerow(["plain", "with,comma", 'with "quote"', "line\nbreak", ""]))
w.writerow([1, 2, 3])
w.writerow([1.5, -0.25])
w.writerow([""])
w.writerow([True, False])
w.writerows([["a", "b"], ["c", "d"]])
print(repr(buf.getvalue()))

b2 = io.StringIO()
w2 = csv.writer(b2, delimiter="\t", quoting=csv.QUOTE_ALL, lineterminator="\n")
w2.writerow(["x", "y z"])
w3 = csv.writer(b2, quoting=csv.QUOTE_NONNUMERIC)
w3.writerow(["s", "t"])
w3.writerow([1.0, 2.0])
w4 = csv.writer(b2, quoting=csv.QUOTE_NONE, escapechar="\\")
w4.writerow(["a,b", 'q"'])
print(repr(b2.getvalue()))

for row in csv.reader(io.StringIO(buf.getvalue())):
    print(row)

out = io.StringIO()
dw = csv.DictWriter(out, fieldnames=["first", "last"], restval="?")
dw.writeheader()
dw.writerow({"first": "Ada", "last": "Lovelace"})
dw.writerow({"first": "Alan"})
print(repr(out.getvalue()))
for d in csv.DictReader(io.StringIO(out.getvalue())):
    print(d, d["first"])
for d in csv.DictReader(["1;2", "", "3;4"], fieldnames=["a", "b"], delimiter=";"):
    print(d)

path = "csv_demo_tmp.csv"
with open(path, "w", newline="") as f:
    fw = csv.writer(f)
    fw.writerow(["id", "note"])
    fw.writerow(["1", "a, b"])
    fw.writerow(["2", "x\ny"])
with open(path, newline="") as f:
    for row in csv.reader(f):
        print(row)
with open(path) as f:
    print(repr(f.read()))
os.remove(path)

s = io.StringIO("one\ntwo\nthree")
print(s.readline(), s.tell(), s.read(3), s.readlines(), s.read())
s.seek(0)
print([line for line in s])
s.seek(1)
s.write("XY")
print(s.getvalue(), s.tell())
s.seek(0, 2)
s.write("!")
print(s.getvalue(), s.truncate(4), s.getvalue())

for k in range(2):
    try:
        if k == 0:
            csv.writer(io.StringIO(), quoting=csv.QUOTE_NONE).writerow(["a,b"])
        else:
            s.close()
            s.write("x")
    except csv.Error as e:
        print("csv.Error", e)
    except ValueError as e:
        print("ValueError", e)
