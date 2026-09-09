/* freetrackclient.dll -- SimTrack's FreeTrack 2.0 client.
 *
 * FreeTrack-aware games (ETS2, ATS, BeamNG, ...) locate this DLL through
 * HKCU\Software\FreeTrack\FreeTrackClient\Path and poll FTGetData() for the
 * pose that the tracker publishes in the FT_SharedMem mapping -- the same
 * block SimTrack's freetrack.py writes (see that file for the layout).
 *
 * Written for SimTrack against the publicly documented interface; see
 * PROVENANCE.txt in this directory.
 */

#include <windows.h>
#include <stdint.h>
#include <string.h>

typedef struct FTData {
    int32_t DataID;
    int32_t CamWidth, CamHeight;
    float Yaw, Pitch, Roll, X, Y, Z;            /* radians / mm */
    float RawYaw, RawPitch, RawRoll, RawX, RawY, RawZ;
    float X1, Y1, X2, Y2, X3, Y3, X4, Y4;
} FTData;

typedef struct FTHeap {
    FTData data;
    int32_t GameID;
    unsigned char table[8];
    int32_t GameID2;
} FTHeap;

#define FT_EXPORT(t) __declspec(dllexport) t __stdcall

static HANDLE  mapping = NULL;
static FTHeap *heap    = NULL;
static HANDLE  mutex   = NULL;

static BOOL ensure_open(void)
{
    if (heap)
        return TRUE;
    mapping = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE,
                                 0, sizeof(FTHeap), "FT_SharedMem");
    if (!mapping)
        return FALSE;
    heap = (FTHeap *) MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0,
                                    sizeof(FTHeap));
    if (!heap) {
        CloseHandle(mapping);
        mapping = NULL;
        return FALSE;
    }
    mutex = CreateMutexA(NULL, FALSE, "FT_Mutext");  /* sic, historic name */
    return TRUE;
}

FT_EXPORT(BOOL) FTGetData(FTData *data)
{
    if (!ensure_open())
        return FALSE;
    if (mutex && WaitForSingleObject(mutex, 16) == WAIT_OBJECT_0) {
        memcpy(data, &heap->data, sizeof *data);
        /* Guard the frame counter against wrapping into negatives on the
         * game side; the tracker restarts it from zero. */
        if (heap->data.DataID > (1 << 29))
            heap->data.DataID = 0;
        ReleaseMutex(mutex);
    }
    return TRUE;
}

FT_EXPORT(void) FTReportName(int name) { (void) name; }
FT_EXPORT(void) FTReportID(int name)   { (void) name; }

FT_EXPORT(const char *) FTGetDllVersion(void) { return "1.0.0.0"; }
FT_EXPORT(const char *) FTProvider(void)      { return "FreeTrack"; }
