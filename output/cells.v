// Behavioural models of the cells used by the synthesized netlists.
module NAND2(input A, input B, output Y); assign Y = ~(A & B); endmodule
module NOR2 (input A, input B, output Y); assign Y = ~(A | B); endmodule
module TIE0 (output Y); assign Y = 1'b0; endmodule
module TIE1 (output Y); assign Y = 1'b1; endmodule
