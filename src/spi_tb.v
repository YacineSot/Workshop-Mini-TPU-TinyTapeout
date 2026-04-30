//`timescale 1ps/1ps


module spi_tb;
    reg rst_n;
    reg mosi;
    reg cs;
    reg sclk;
    wire data_ready;
    wire [3:0] data_buffer;
    wire [3:0] addr_counter;

    spi uut_spi (
        .clk(sclk),
        .rst_n(rst_n),
        .mosi(mosi),
        .cs(cs),
        .sclk(sclk),
        .data_ready(data_ready),
        .data_buffer(data_buffer),
        .addr_counter(addr_counter)
    );


    //always #5 sclk = ~sclk; // Generate clock signal 

    initial begin
        // Initialize signals
        rst_n = 1;
        #10
        rst_n = 0;
        mosi = 0;
        cs = 1; // Active low
        sclk = 0;
        // Reset the system
        #10 rst_n = 1;

        // Simulate SPI communication
        for (integer i = 0; i < 16; i = i + 1) begin
             #10 cs = 0; // Start communication
             // Send 4 bits of data (e.g., 1010)
             $display("-----------|--------------");
             $display(" DATA 4-bit (3:0) | Data Ready | Address Counter");
             $display("-----------|-------------|------------------");
             #10 mosi = i[0]; sclk = 1; #10 sclk = 0; // Bit 1
             $display("%b | %b | %b", data_buffer, data_ready, addr_counter);
             #10 mosi = i[1]; sclk = 1; #10 sclk = 0; // Bit 2
             $display("%b | %b | %b", data_buffer, data_ready, addr_counter);
             #10 mosi = i[2]; sclk = 1; #10 sclk = 0; // Bit 3
             $display("%b | %b | %b", data_buffer, data_ready, addr_counter);
             #10 mosi = i[3]; sclk = 1; #10 sclk = 0; // Bit 4
             $display("%b | %b | %b", data_buffer, data_ready, addr_counter);

             #10 cs = 1; // End communication

             // Wait for data to be ready
             #20;
        end
    end
    //$finish;
    //$stop;
endmodule