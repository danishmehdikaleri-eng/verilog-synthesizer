module mux16(
    input d0,
    input d1,
    input d2,
    input d3,
    input d4,
    input d5,
    input d6,
    input d7,
    input d8,
    input d9,
    input d10,
    input d11,
    input d12,
    input d13,
    input d14,
    input d15,
    input s0,
    input s1,
    input s2,
    input s3,
    output y
);

assign y = (s3?(s2?(s1?(s0?d15:d14):(s0?d13:d12)):(s1?(s0?d11:d10):(s0?d9:d8))):(s2?(s1?(s0?d7:d6):(s0?d5:d4)):(s1?(s0?d3:d2):(s0?d1:d0))));

endmodule
