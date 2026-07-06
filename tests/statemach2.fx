#import <standard.fx>;

using standard::io::console;

enum State { Idle, Running, Paused, Stopped, Unknown};

comptime
{
    int[] trans_from = [0, 1, 2, 1];
    int[] trans_to   = [1, 2, 1, 3];
    int   tcount     = 4;

    emitflux
    {
        def state_name(int s) -> byte*
        {
            if (s == 0) { return $State.Idle; };
            if (s == 1) { return $State.Running; };
            if (s == 2) { return $State.Paused; };
            if (s == 3) { return $State.Stopped; };
            return $State.Unknown;
        };
    };

    for (int tidx = 0; tidx < tcount; tidx++)
    {
        emitflux
        {
            def ~$i"can_trans_{}_{}":{trans_from[tidx];trans_to[tidx];}() -> bool { return true; };
        };
    };

    emitflux
    {
        def transition(int fx, int to) -> int
        {
            if (fx == 0 & to == 1 & can_trans_0_1()) { return to; };
            if (fx == 1 & to == 2 & can_trans_1_2()) { return to; };
            if (fx == 2 & to == 1 & can_trans_2_1()) { return to; };
            if (fx == 1 & to == 3 & can_trans_1_3()) { return to; };
            println(f"Invalid: {state_name(fx)} -> {state_name(to)}");
            return fx;
        };
    };
};

def main() -> int
{
    int state = 0;

    println(f"Initial: {state_name(state)}");

    state = transition(state, 1);
    println(f"Start:   {state_name(state)}");

    state = transition(state, 2);
    println(f"Pause:   {state_name(state)}");

    state = transition(state, 3);
    println(f"Invalid: {state_name(state)}");

    state = transition(state, 1);
    println(f"Resume:  {state_name(state)}");

    state = transition(state, 3);
    println(f"Stop:    {state_name(state)}");

    state = transition(state, 4);
    println(f"Unknown: {state_name(state)}");

    return 0;
};
