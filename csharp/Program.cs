// Program.cs (.NET 8)
string path = args[0], mode = args[1];
long[] offsets = File.ReadLines("offsets.txt").Select(long.Parse).ToArray();
var buffer = new byte[100];

if (mode == "stream")
{
    using var fs = new FileStream(path, FileMode.Open, FileAccess.Read);
    foreach (long offset in offsets)
    {
        fs.Seek(offset, SeekOrigin.Begin);
        fs.ReadExactly(buffer);
    }
}
else
{
    using var handle = File.OpenHandle(path);
    foreach (long offset in offsets)
        RandomAccess.Read(handle, buffer, offset);
}
