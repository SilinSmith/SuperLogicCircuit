// 本文件由 rvgen 1.0.0 生成；生成区每次整体重写，请勿手改。
// rvgen:fingerprint 8f4e925ce8f66c49a515dd7968b04962f4f0ae3c838ee725807c4bf9f3747dc7
`timescale 1ns/1ps
module top (
    input wire clk,
    input wire [7:0] cfg,
    input wire rxd,
    input wire [7:0] push,
    output wire tx,
    output wire [7:0] pop,
    output wire baud_tick
);
    uart #(
        .WIDTH(8)
    ) u_uart (
        .clk(clk),
        .cfg(cfg),
        .rxd(rxd),
        .tx(tx)
    );
// rvgen:user-begin inst.uart
    // TODO(rvgen): 该实例的附加逻辑写在这里
// rvgen:user-end inst.uart
    fifo u_fifo (
        .clk(clk),
        .push(push),
        .pop(pop)
    );
// rvgen:user-begin inst.fifo
    // TODO(rvgen): 该实例的附加逻辑写在这里
// rvgen:user-end inst.fifo
    baud_gen u_baud_gen (
        .clk(clk),
        .tick(baud_tick)
    );
// rvgen:user-begin inst.baud_gen
    // TODO(rvgen): 该实例的附加逻辑写在这里
// rvgen:user-end inst.baud_gen
endmodule
