// 3x3 systolic array of processing elements
// Array dimensions reduced from 4x4 to fit a TinyTapeout 1x1 tile.

`define DATA_WIDTH 4
`define ACC_WIDTH  4
`define N 3                    // array size (NxN)
`define NN 9                   // N*N for the flattened output

module array (
    input  wire                       clk,
    input  wire                       rst_n,
    input  wire                       we,

    input  wire [`DATA_WIDTH*`N-1:0]   a_in,    // N rows of activations
    input  wire [`DATA_WIDTH*`N-1:0]   b_in,    // N columns of weights
    output wire [`ACC_WIDTH*`NN-1:0]   data_out
);

    // a_pipe[row][col] : activation flowing right (last col is the rightmost a_out)
    wire [`DATA_WIDTH-1:0] a_pipe [0:`N-1][0:`N];
    // b_pipe[row][col] : weight flowing down (last row is the bottom b_out)
    wire [`DATA_WIDTH-1:0] b_pipe [0:`N][0:`N-1];

    // c_bus[row][col] : accumulation outputs
    wire [`ACC_WIDTH-1:0]  c_bus  [0:`N-1][0:`N-1];

    genvar row, col;
    generate
        for (row = 0; row < `N; row = row + 1) begin : map_a_in
            assign a_pipe[row][0] = a_in[`DATA_WIDTH*(row+1)-1:`DATA_WIDTH*row];
        end
        for (col = 0; col < `N; col = col + 1) begin : map_b_in
            assign b_pipe[0][col] = b_in[`DATA_WIDTH*(col+1)-1:`DATA_WIDTH*col];
        end
    endgenerate

    generate
        for (row = 0; row < `N; row = row + 1) begin : ROWS
            for (col = 0; col < `N; col = col + 1) begin : COLS
                pe pe_inst (
                    .clk   (clk),
                    .rst_n (rst_n),
                    .we    (we),
                    .a_in  (a_pipe[row][col]),
                    .b_in  (b_pipe[row][col]),
                    .a_out (a_pipe[row][col+1]),
                    .b_out (b_pipe[row+1][col]),
                    .c_out (c_bus [row][col])
                );
            end
        end
    endgenerate

    // Flatten c_bus into data_out (row-major)
    generate
        for (row = 0; row < `N; row = row + 1) begin : flat_row
            for (col = 0; col < `N; col = col + 1) begin : flat_col
                localparam flat_idx = row*`N + col;
                assign data_out[`ACC_WIDTH*(flat_idx+1)-1:`ACC_WIDTH*flat_idx] = c_bus[row][col];
            end
        end
    endgenerate

endmodule
