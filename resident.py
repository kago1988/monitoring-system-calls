"""Print how many 4 KiB pages of a file are in the page cache (mincore)."""
import ctypes, os, sys
libc = ctypes.CDLL("libc.so.6", use_errno=True)
libc.mmap.restype = ctypes.c_void_p
libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_ubyte)]
libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
path = sys.argv[1]
size = os.path.getsize(path)
fd = os.open(path, os.O_RDONLY)
addr = libc.mmap(None, size, 1, 1, fd, 0)  # PROT_READ, MAP_SHARED
pages = (size + 4095) // 4096
vec = (ctypes.c_ubyte * pages)()
assert libc.mincore(addr, size, vec) == 0, ctypes.get_errno()
libc.munmap(addr, size); os.close(fd)
print(sum(v & 1 for v in vec), "of", pages, "pages resident")
