module comparator4_nor(
    input a3,
    input a2,
    input a1,
    input a0,
    input b3,
    input b2,
    input b1,
    input b0,
    output eq,
    output gt,
    output lt
);

wire n1, n2, n3, n4, n5, n6, n7, n8, n9, n10, n11, n12, n13, n14, n15, n16, n17, n18, n19, n20, n21, n22, n23, n24, n25, n26, n27, n28, n29, n30, n31, n32, n33, n34, n35, n36, n37, n38, n39, n40, n41, n42, n43, n44, n45, n46, n47, n48, n49, n50, n51, n52, n53, n54;

NOR2 u_n1 (.A(a3), .B(b3), .Y(n1));
NOR2 u_n2 (.A(a3), .B(a3), .Y(n2));
NOR2 u_n3 (.A(b3), .B(b3), .Y(n3));
NOR2 u_n4 (.A(n2), .B(n3), .Y(n4));
NOR2 u_n5 (.A(n1), .B(n4), .Y(n5));
NOR2 u_n6 (.A(a2), .B(b2), .Y(n6));
NOR2 u_n7 (.A(a2), .B(a2), .Y(n7));
NOR2 u_n8 (.A(b2), .B(b2), .Y(n8));
NOR2 u_n9 (.A(n7), .B(n8), .Y(n9));
NOR2 u_n10 (.A(n6), .B(n9), .Y(n10));
NOR2 u_n11 (.A(n5), .B(n10), .Y(n11));
NOR2 u_n12 (.A(a1), .B(b1), .Y(n12));
NOR2 u_n13 (.A(a1), .B(a1), .Y(n13));
NOR2 u_n14 (.A(b1), .B(b1), .Y(n14));
NOR2 u_n15 (.A(n13), .B(n14), .Y(n15));
NOR2 u_n16 (.A(n12), .B(n15), .Y(n16));
NOR2 u_n17 (.A(n11), .B(n11), .Y(n17));
NOR2 u_n18 (.A(n17), .B(n16), .Y(n18));
NOR2 u_n19 (.A(a0), .B(b0), .Y(n19));
NOR2 u_n20 (.A(a0), .B(a0), .Y(n20));
NOR2 u_n21 (.A(b0), .B(b0), .Y(n21));
NOR2 u_n22 (.A(n20), .B(n21), .Y(n22));
NOR2 u_n23 (.A(n19), .B(n22), .Y(n23));
NOR2 u_n24 (.A(n18), .B(n18), .Y(n24));
NOR2 u_eq (.A(n24), .B(n23), .Y(eq));
NOR2 u_n25 (.A(n2), .B(b3), .Y(n25));
NOR2 u_n26 (.A(n5), .B(n7), .Y(n26));
NOR2 u_n27 (.A(n26), .B(n26), .Y(n27));
NOR2 u_n28 (.A(n27), .B(b2), .Y(n28));
NOR2 u_n29 (.A(n25), .B(n28), .Y(n29));
NOR2 u_n30 (.A(n29), .B(n29), .Y(n30));
NOR2 u_n31 (.A(n17), .B(n13), .Y(n31));
NOR2 u_n32 (.A(n31), .B(n31), .Y(n32));
NOR2 u_n33 (.A(n32), .B(b1), .Y(n33));
NOR2 u_n34 (.A(n30), .B(n33), .Y(n34));
NOR2 u_n35 (.A(n34), .B(n34), .Y(n35));
NOR2 u_n36 (.A(n24), .B(n20), .Y(n36));
NOR2 u_n37 (.A(n36), .B(n36), .Y(n37));
NOR2 u_n38 (.A(n37), .B(b0), .Y(n38));
NOR2 u_n39 (.A(n35), .B(n38), .Y(n39));
NOR2 u_gt (.A(n39), .B(n39), .Y(gt));
NOR2 u_n40 (.A(a3), .B(n3), .Y(n40));
NOR2 u_n41 (.A(n5), .B(a2), .Y(n41));
NOR2 u_n42 (.A(n41), .B(n41), .Y(n42));
NOR2 u_n43 (.A(n42), .B(n8), .Y(n43));
NOR2 u_n44 (.A(n40), .B(n43), .Y(n44));
NOR2 u_n45 (.A(n44), .B(n44), .Y(n45));
NOR2 u_n46 (.A(n17), .B(a1), .Y(n46));
NOR2 u_n47 (.A(n46), .B(n46), .Y(n47));
NOR2 u_n48 (.A(n47), .B(n14), .Y(n48));
NOR2 u_n49 (.A(n45), .B(n48), .Y(n49));
NOR2 u_n50 (.A(n49), .B(n49), .Y(n50));
NOR2 u_n51 (.A(n24), .B(a0), .Y(n51));
NOR2 u_n52 (.A(n51), .B(n51), .Y(n52));
NOR2 u_n53 (.A(n52), .B(n21), .Y(n53));
NOR2 u_n54 (.A(n50), .B(n53), .Y(n54));
NOR2 u_lt (.A(n54), .B(n54), .Y(lt));

endmodule
