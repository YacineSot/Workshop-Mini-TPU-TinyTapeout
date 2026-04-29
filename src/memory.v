// 3x3 register-file memory for the Mini TPU.
// Reset removed: cells are written via LOAD before any read.
// Read pattern is staggered per row to feed the systolic array.

`define DATA_WIDTH 4
`define N 3

module memory (
    input wire clk,
    input wire rst_n,                                 // unused, kept on the interface
    input wire write_enable,
    input wire [1:0] write_line,                      // log2(N) bits, but 2 is fine for N<=4
    input wire [1:0] write_elem,
    input wire [`DATA_WIDTH-1:0] data_in,
    input wire [`N-1:0]      read_enable,
    input wire [`N*2-1:0]    read_elem,               // 2-bit selector per row
    output wire [`DATA_WIDTH*`N-1:0] data_out
);

    reg [`DATA_WIDTH-1:0] mem [`N-1:0][`N-1:0];

    wire [1:0]                read_elem_array  [`N-1:0];
    wire [`DATA_WIDTH-1:0]    data_out_array   [`N-1:0];

    genvar i;
    generate
        for (i = 0; i < `N; i = i + 1) begin : map_read_elem
            assign read_elem_array[i] = read_elem[i*2+1:i*2];
        end
        for (i = 0; i < `N; i = i + 1) begin : map_data_out
            assign data_out[`DATA_WIDTH*(i+1)-1:`DATA_WIDTH*i] = data_out_array[i];
        end
    endgenerate

    // Synchronous addressed write — addresses outside [0, N-1] are silently ignored.
    always @(posedge clk) begin
        if (write_enable && write_line < `N && write_elem < `N) begin
            mem[write_line][write_elem] <= data_in;
        end
    end

    generate
        for (i = 0; i < `N; i = i + 1) begin : read_output_gen
            assign data_out_array[i] = read_enable[i] ?
                                        mem[i][read_elem_array[i]] :
                                        {`DATA_WIDTH{1'b0}};
        end
    endgenerate

    wire _unused_rstn = rst_n;

endmodule
