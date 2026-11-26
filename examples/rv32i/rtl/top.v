// 本文件由 slc 1.0.2 生成；生成区每次整体重写，请勿手改。
// slc:fingerprint 175248d30b5c44af18b98ecdb4926c0edb83efb62815e3f0afd2eb315abd0571
`timescale 1ns/1ps
module top (
    input wire clk,
    input wire rst_n,
    input wire [31:0] instr,
    output wire [31:0] result,
    output wire icache_ready,
    output wire dcache_ready
);
    wire [31:0] w_if_stage_dout;
    wire [31:0] w_id_stage_dout;
    wire [31:0] w_ex_stage_dout;
    wire [31:0] w_mem_stage_dout;
    if_stage u_if_stage (
        .clk(clk),
        .rst_n(rst_n),
        .din(instr),
        .dout(w_if_stage_dout)
    );
// slc:user-begin inst.if_stage
    // TODO(slc): 该实例的附加逻辑写在这里
// slc:user-end inst.if_stage
    id_stage u_id_stage (
        .clk(clk),
        .rst_n(rst_n),
        .din(w_if_stage_dout),
        .dout(w_id_stage_dout)
    );
// slc:user-begin inst.id_stage
    // TODO(slc): 该实例的附加逻辑写在这里
// slc:user-end inst.id_stage
    ex_stage u_ex_stage (
        .clk(clk),
        .rst_n(rst_n),
        .din(w_id_stage_dout),
        .dout(w_ex_stage_dout)
    );
// slc:user-begin inst.ex_stage
    // TODO(slc): 该实例的附加逻辑写在这里
// slc:user-end inst.ex_stage
    mem_stage u_mem_stage (
        .clk(clk),
        .rst_n(rst_n),
        .din(w_ex_stage_dout),
        .dout(w_mem_stage_dout)
    );
// slc:user-begin inst.mem_stage
    // TODO(slc): 该实例的附加逻辑写在这里
// slc:user-end inst.mem_stage
    wb_stage u_wb_stage (
        .clk(clk),
        .rst_n(rst_n),
        .din(w_mem_stage_dout),
        .dout(result)
    );
// slc:user-begin inst.wb_stage
    // TODO(slc): 该实例的附加逻辑写在这里
// slc:user-end inst.wb_stage
    icache u_icache (
        .clk(clk),
        .rst_n(rst_n),
        .req('0),
        .ready(icache_ready)
    );
// slc:user-begin inst.icache
    // TODO(slc): 该实例的附加逻辑写在这里
// slc:user-end inst.icache
    dcache u_dcache (
        .clk(clk),
        .rst_n(rst_n),
        .req('0),
        .ready(dcache_ready)
    );
// slc:user-begin inst.dcache
    // TODO(slc): 该实例的附加逻辑写在这里
// slc:user-end inst.dcache
endmodule
