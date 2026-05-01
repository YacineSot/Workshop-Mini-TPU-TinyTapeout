// SPI slave that captures 16-bit MSB-first frames and presents them on
// spi_instr while SS_n is high. While SS_n is low (frame in progress)
// spi_instr is forced to NOP (16'h0000) so the chip's RUN counter does
// not advance during the next frame's shift-in. SPI mode 0 (CPOL=0,
// CPHA=0): MOSI sampled on SCK rising edge. All async inputs are
// 3-stage synchronized; chip clk must be >= ~4x SCK.
//
// Timing (cycles measured at the chip clock):
//   * SS_n falling: ~3 cycles after the wire transition before
//     spi_instr drops to NOP.
//   * SS_n rising:  ~3 cycles after the wire transition before the
//     newly latched instruction appears on spi_instr.
// So the host should ensure SS_n stays high long enough between frames
// for the chip to take any cycle-counted action (e.g. RUN).

`timescale 1ns/1ps

module spi_loader (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        sck,
    input  wire        mosi,
    input  wire        ss_n,
    output wire [15:0] spi_instr
);

    reg [2:0] sck_sync;
    reg [2:0] ss_sync;
    reg [1:0] mosi_sync;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sck_sync  <= 3'b000;
            ss_sync   <= 3'b111;
            mosi_sync <= 2'b00;
        end else begin
            sck_sync  <= {sck_sync[1:0], sck};
            ss_sync   <= {ss_sync[1:0], ss_n};
            mosi_sync <= {mosi_sync[0], mosi};
        end
    end

    wire sck_rising = (sck_sync[2:1] == 2'b01);
    wire ss_low     = ~ss_sync[2];
    wire ss_rising  = (ss_sync[2:1] == 2'b01);

    reg [15:0] shift_reg;
    reg [15:0] latched;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            shift_reg <= 16'h0000;
            latched   <= 16'h0000;
        end else begin
            if (sck_rising && ss_low) begin
                shift_reg <= {shift_reg[14:0], mosi_sync[1]};
            end
            if (ss_rising) begin
                latched <= shift_reg;
            end
        end
    end

    // While SS_n is asserted (synced low) the bus is forced to NOP so
    // that the next frame's shift-in time does not extend the previous
    // instruction. Between frames (SS_n high) the latched value drives
    // the bus, which is what gives RUN its multi-cycle drain window.
    assign spi_instr = ss_sync[2] ? latched : 16'h0000;

endmodule
