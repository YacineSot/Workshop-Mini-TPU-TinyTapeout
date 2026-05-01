`timescale 1ps/1ps
`define DATA_WIDTH 4
`define INST_WIDTH 12

module tpu_interface_tb;
    reg clk;
    reg rst_n;
    reg mosi;
    reg cs;
    reg sclk;
    reg [`INST_WIDTH-1:0] instruction;
    wire [7:0] result;
    integer i;
    integer j;


    tpu_interface uut_tpu_interface (
        .clk(clk),
        .rst_n(rst_n),
        .mosi(mosi),
        .cs(cs),
        .sclk(sclk),
        .result(result)
    );
    initial begin
        $dumpfile("tpu_interface_tb.vcd");
        $dumpvars(0, tpu_interface_tb);
    end
    //always #5 sclk = ~sclk; // Generate clock signal 
    always #20 clk = ~clk; // Generate clock signal
    initial begin
        // Initialize signals
        clk = 0;
        rst_n = 0;
        mosi = 0;
        cs = 1; // Active low
        sclk = 0;
        instruction = 12'b1000_0000_1111; // Example instruction
        // Reset the system
        #10 rst_n = 1;

        // Simulate SPI communication
        #10 cs = 0; // Start communication
        // Send 4 bits of data (e.g., 1010)
        for ( j = 0; j<9; j=j+1) begin
            instruction = {4'b1000,j[3:0], 4'b1111};
            for(i = 0; i < `INST_WIDTH; i = i + 1) begin
                #40 mosi = instruction[i]; sclk = 1; #40 sclk = 0; // Shift in bits
            end
        end
        #10
        for ( j = 0; j<9; j=j+1) begin
            instruction = {4'b1010,j[3:0], 4'b1010};
            for(i = 0; i < `INST_WIDTH; i = i + 1) begin
                #40 mosi = instruction[i]; sclk = 1; #40 sclk = 0; // Shift in bits
            end
        end

        // #10 cs = 0;
        // instruction = 12'b1100_0000_0000; // store instruction
        // for( i = 0; i < 12; i = i + 1) begin
        //      #10 mosi = instruction[i]; sclk = 1; #10 sclk = 0; // Shift in bits
        // end
        // #50 cs = 1;
        instruction = 12'b0100_0000_0000; // run instruction
        for( i = 0; i < `INST_WIDTH; i = i + 1) begin
             #40 mosi = instruction[i]; sclk = 1; #40 sclk = 0; // Shift in bits
        end
        #50 cs = 0;

        for (i = 0; i<200; i = i + 1) begin
            #40 sclk = 1; #40 sclk = 0; // Shift in bits
        end

        // Wait for data to be ready
        #100;
    end
    //$finish;
    //$stop;
    //$finish;
    //$stop;
endmodule