/* Render an original Amiga module through the separately installed libuade.
 * Build: cc render_music.c $(pkg-config --cflags --libs libuade) -o render_music
 * Usage: render_music module output.wav subsong seconds
 */
#include <uade/uade.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>

static void le32(FILE* f, uint32_t value)
{
    unsigned i;
    for (i = 0; i < 4; ++i) fputc((value >> (8 * i)) & 255, f);
}

static void header(FILE* f, unsigned rate, uint32_t bytes)
{
    fwrite("RIFF", 1, 4, f); le32(f, bytes + 36);
    fwrite("WAVEfmt ", 1, 8, f); le32(f, 16);
    fwrite("\x01\x00\x02\x00", 1, 4, f); le32(f, rate);
    le32(f, rate * 4); fwrite("\x04\x00\x10\x00", 1, 4, f);
    fwrite("data", 1, 4, f); le32(f, bytes);
}

int main(int argc, char** argv)
{
    struct uade_state* state;
    struct uade_config* config;
    const struct uade_song_info* info;
    FILE* output;
    int16_t buffer[2048];
    uint32_t bytes = 0, limit;
    long song, seconds;
    char *end;
    int rate, failed = 0;
    if (argc != 5) { fprintf(stderr, "Usage: %s module output.wav subsong seconds\n", argv[0]); return 2; }
    song = strtol(argv[3], &end, 10);
    if (*end || song < 0 || song > 31) return 2;
    seconds = strtol(argv[4], &end, 10);
    if (*end || seconds < 1 || seconds > 600) return 2;
    signal(SIGPIPE, SIG_IGN);
    config = uade_new_config();
    if (!config) return 1;
    uade_config_set_option(config, UC_ONE_SUBSONG, NULL);
    uade_config_set_option(config, UC_NO_CONTENT_DB, NULL);
    state = uade_new_state(config);
    if (!state) return 1;
    if (uade_play(argv[1], (int)song, state) != 1) { uade_cleanup_state(state); return 1; }
    info = uade_get_song_info(state);
    fprintf(stderr, "Player: %s; format: %s; subsongs: %d..%d; selected: %d\n",
            info->playername, info->formatname, info->subsongs.min, info->subsongs.max, info->subsongs.cur);
    rate = uade_get_sampling_rate(state);
    if (rate <= 0 || rate > 192000) { uade_cleanup_state(state); return 1; }
    limit = (uint32_t)rate * 4 * seconds;
    output = fopen(argv[2], "wbx");
    if (!output) { perror(argv[2]); uade_cleanup_state(state); return 1; }
    header(output, rate, 0);
    while (bytes < limit) {
        size_t want = limit - bytes < sizeof buffer ? limit - bytes : sizeof buffer;
        ssize_t got = uade_read(buffer, want, state);
        size_t i;
        if (got < 0 || got % 4) { failed = 1; break; }
        if (!got) break;
        for (i = 0; i < (size_t)got / 2; ++i) {
            uint16_t sample = (uint16_t)buffer[i];
            fputc(sample & 255, output); fputc(sample >> 8, output);
        }
        bytes += (uint32_t)got;
        if (ferror(output)) { failed = 1; break; }
    }
    if (fseek(output, 0, SEEK_SET)) failed = 1;
    header(output, rate, bytes);
    if (fclose(output)) failed = 1;
    uade_cleanup_state(state);
    if (failed || !bytes) { remove(argv[2]); return 1; }
    fprintf(stderr, "Wrote %.3f seconds, %u Hz stereo PCM to %s (bounded preview, not asserted complete)\n",
            (double)bytes / (rate * 4), rate, argv[2]);
    return 0;
}
